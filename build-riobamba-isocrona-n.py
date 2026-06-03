import heapq
import json
import math
from pathlib import Path

import networkx as nx
import requests
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, shape, mapping
from shapely.ops import transform, unary_union


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
PLATFORMS_PATH = DATA_DIR / "riobamba_plataformas.geojson"
EQUIPAMIENTOS_PATH = DATA_DIR / "riobamba_equipamientos.geojson"
OUTPUT_ISOCHRONE = DATA_DIR / "riobamba_isocrona_plataforma_n.geojson"
OUTPUT_ORIGINS = DATA_DIR / "riobamba_isocrona_plataforma_n_origenes.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba_isocrona_plataforma_n_stats.json"

TARGET_PLATFORM = "PLATAFORMA Ñ"
DISTANCE_METERS = 1250
BUFFER_METERS = 1700
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WALKABLE_HIGHWAYS = {
    "footway", "path", "pedestrian", "living_street", "residential", "service",
    "tertiary", "tertiary_link", "secondary", "secondary_link", "primary",
    "primary_link", "unclassified", "track", "cycleway", "steps"
}
BLOCKED_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed"}


transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True)
transformer_to_wgs = Transformer.from_crs("EPSG:32717", "EPSG:4326", always_xy=True)


def load_geojson(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def to_utm(geom):
    return transform(transformer_to_utm.transform, geom)


def to_wgs84(geom):
    return transform(transformer_to_wgs.transform, geom)


def is_walkable(tags):
    highway = tags.get("highway")
    if not highway or highway in BLOCKED_HIGHWAYS:
        return False
    if highway not in WALKABLE_HIGHWAYS:
        return False
    if tags.get("access") == "private":
        return False
    if tags.get("foot") in {"no", "private"}:
        return False
    return True


def fetch_osm_ways(bounds):
    minx, miny, maxx, maxy = bounds
    x_mid = (minx + maxx) / 2
    y_mid = (miny + maxy) / 2
    tiles = [
        (minx, miny, x_mid, y_mid),
        (x_mid, miny, maxx, y_mid),
        (minx, y_mid, x_mid, maxy),
        (x_mid, y_mid, maxx, maxy),
    ]

    merged = {}

    for west, south, east, north in tiles:
        query = (
            f'[out:json][timeout:120];'
            f'way["highway"]({south},{west},{north},{east});'
            f'out geom;'
        )
        response = requests.post(
            OVERPASS_URL,
            data=query,
            timeout=180,
            headers={
                "Content-Type": "text/plain",
                "User-Agent": "codex-riobamba-isochrone/1.0",
            },
        )
        response.raise_for_status()
        payload = response.json()
        for element in payload.get("elements", []):
            merged[element["id"]] = element

    return {"elements": list(merged.values())}


def build_graph(overpass_json):
    graph = nx.Graph()
    edge_lines = []

    for element in overpass_json.get("elements", []):
      if element.get("type") != "way":
          continue

      tags = element.get("tags", {})
      if not is_walkable(tags):
          continue

      geometry = element.get("geometry", [])
      if len(geometry) < 2:
          continue

      coords_wgs = [(item["lon"], item["lat"]) for item in geometry]
      coords_utm = [transformer_to_utm.transform(lon, lat) for lon, lat in coords_wgs]

      for idx in range(len(coords_utm) - 1):
          start = coords_utm[idx]
          end = coords_utm[idx + 1]
          length = math.dist(start, end)
          if length <= 0:
              continue

          start_id = ("xy", round(start[0], 3), round(start[1], 3))
          end_id = ("xy", round(end[0], 3), round(end[1], 3))

          graph.add_node(start_id, x=start[0], y=start[1])
          graph.add_node(end_id, x=end[0], y=end[1])
          graph.add_edge(start_id, end_id, weight=length)

          edge_lines.append(LineString([start, end]))

    return graph, edge_lines


def nearest_node(point_xy, nodes):
    px, py = point_xy
    best = None
    best_dist = float("inf")
    for node_id, attrs in nodes:
        dist = math.dist((attrs["x"], attrs["y"]), (px, py))
        if dist < best_dist:
            best = node_id
            best_dist = dist
    return best, best_dist


def multi_source_reachable(graph, source_nodes, cutoff):
    distances = {node: 0.0 for node in source_nodes}
    heap = [(0.0, node) for node in source_nodes]
    heapq.heapify(heap)

    while heap:
        current_dist, node = heapq.heappop(heap)
        if current_dist > distances.get(node, float("inf")):
            continue
        if current_dist > cutoff:
            continue

        for neighbor, attrs in graph[node].items():
            weight = float(attrs.get("weight", 0.0))
            candidate = current_dist + weight
            if candidate > cutoff:
                continue
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                heapq.heappush(heap, (candidate, neighbor))

    return distances


def build_isochrone_polygon(graph, distances, cutoff):
    node_buffers = []
    edge_buffers = []

    for node_id, dist in distances.items():
        attrs = graph.nodes[node_id]
        node_buffers.append(Point(attrs["x"], attrs["y"]).buffer(22))

    for start, end, attrs in graph.edges(data=True):
        d1 = distances.get(start)
        d2 = distances.get(end)
        if d1 is None and d2 is None:
            continue

        if d1 is not None and d2 is not None:
            edge_buffers.append(LineString([
                (graph.nodes[start]["x"], graph.nodes[start]["y"]),
                (graph.nodes[end]["x"], graph.nodes[end]["y"])
            ]).buffer(18))
            continue

        known_dist = d1 if d1 is not None else d2
        if known_dist is None:
            continue
        remaining = cutoff - known_dist
        if remaining <= 0:
            continue

        length = float(attrs.get("weight", 0.0))
        ratio = min(1.0, remaining / length) if length else 0.0
        sx, sy = graph.nodes[start]["x"], graph.nodes[start]["y"]
        ex, ey = graph.nodes[end]["x"], graph.nodes[end]["y"]
        if d1 is not None:
            mx = sx + (ex - sx) * ratio
            my = sy + (ey - sy) * ratio
            segment = LineString([(sx, sy), (mx, my)])
        else:
            mx = ex + (sx - ex) * ratio
            my = ey + (sy - ey) * ratio
            segment = LineString([(ex, ey), (mx, my)])
        edge_buffers.append(segment.buffer(18))

    merged = unary_union(node_buffers + edge_buffers)
    smoothed = merged.buffer(30).buffer(-20)
    return smoothed


def main():
    platforms_data = load_geojson(PLATFORMS_PATH)
    equipamientos_data = load_geojson(EQUIPAMIENTOS_PATH)

    platform_geoms = {
        feature["properties"]["platform_name"]: shape(feature["geometry"])
        for feature in platforms_data["features"]
    }

    target_geom = platform_geoms[TARGET_PLATFORM]
    neighbor_names = [
        name for name, geom in platform_geoms.items()
        if name != TARGET_PLATFORM and (target_geom.touches(geom) or target_geom.intersects(geom))
    ]
    neighbor_union = unary_union([platform_geoms[name] for name in neighbor_names])

    equipamientos = []
    origin_points = []
    for feature in equipamientos_data["features"]:
        geom = shape(feature["geometry"])
        point = geom.representative_point()
        platform_name = None
        for name in neighbor_names:
            if platform_geoms[name].contains(point) or platform_geoms[name].touches(point):
                platform_name = name
                break
        if not platform_name:
            continue

        equipamientos.append({
            "feature": feature,
            "platform_name": platform_name,
            "point": point,
        })
        origin_points.append(point)

    search_area = to_wgs84(to_utm(neighbor_union).buffer(BUFFER_METERS))
    bounds = search_area.bounds
    overpass_json = fetch_osm_ways(bounds)
    graph, _ = build_graph(overpass_json)
    nodes = list(graph.nodes(data=True))

    source_nodes = []
    source_features = []
    for item in equipamientos:
        point_utm = to_utm(item["point"])
        node_id, snap_distance = nearest_node((point_utm.x, point_utm.y), nodes)
        if node_id is None:
            continue
        source_nodes.append(node_id)
        source_features.append({
            "type": "Feature",
            "properties": {
                "nombre": item["feature"]["properties"]["nombre"],
                "categoria": item["feature"]["properties"]["categoria"],
                "codigo": item["feature"]["properties"]["codigo"],
                "platform_name": item["platform_name"],
                "snap_m": round(snap_distance, 2),
            },
            "geometry": mapping(item["point"]),
        })

    reachable = multi_source_reachable(graph, source_nodes, DISTANCE_METERS)
    polygon_utm = build_isochrone_polygon(graph, reachable, DISTANCE_METERS).simplify(8, preserve_topology=True)
    polygon_wgs = to_wgs84(polygon_utm)

    if isinstance(polygon_wgs, Polygon):
        geometry = mapping(polygon_wgs)
    elif isinstance(polygon_wgs, MultiPolygon):
        geometry = mapping(polygon_wgs)
    else:
        geometry = mapping(polygon_wgs.convex_hull)

    isochrone_feature = {
        "type": "Feature",
        "properties": {
            "nombre": "Isocrona 15 minutos desde equipamientos colindantes a PLATAFORMA Ñ",
            "target_platform": TARGET_PLATFORM,
            "neighbor_platforms": ", ".join(neighbor_names),
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "equipamientos_origen": len(source_features),
            "nodos_alcanzables": len(reachable),
        },
        "geometry": geometry,
    }

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "target_platform": TARGET_PLATFORM,
        "neighbor_platforms": neighbor_names,
        "equipamientos_origen": len(source_features),
        "distance_m": DISTANCE_METERS,
        "mode": "walking",
        "reachable_nodes": len(reachable),
        "source": "OpenStreetMap peatonal + equipamientos de plataformas colindantes",
    }

    with open(OUTPUT_ISOCHRONE, "w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": [isochrone_feature]}, handle, ensure_ascii=False)

    with open(OUTPUT_ORIGINS, "w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": source_features}, handle, ensure_ascii=False)

    with open(OUTPUT_STATS, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    print("Listo.")
    print(f"Vecinas: {neighbor_names}")
    print(f"Equipamientos origen: {len(source_features)}")


if __name__ == "__main__":
    main()
