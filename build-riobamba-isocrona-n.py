import heapq
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import requests
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape, mapping
from shapely.ops import transform, unary_union


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
PLATFORMS_PATH = DATA_DIR / "riobamba_plataformas.geojson"
EQUIPAMIENTOS_PATH = DATA_DIR / "riobamba_equipamientos.geojson"
OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json"

OUTPUT_BY_PLATFORM = DATA_DIR / "riobamba_isocronas_plataformas_colindantes_n.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba_isocronas_plataformas_colindantes_n_stats.json"

TARGET_PLATFORM = "PLATAFORMA " + chr(209)
DISTANCE_METERS = 1250
BUFFER_METERS = 1700
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PRIORITY_CATEGORIES = {"Salud", "Educación", "Seguridad"}
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


def save_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


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


def post_overpass(query):
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
    return response.json()


def subdivide_bounds(bounds):
    minx, miny, maxx, maxy = bounds
    x_mid = (minx + maxx) / 2
    y_mid = (miny + maxy) / 2
    return [
        (minx, miny, x_mid, y_mid),
        (x_mid, miny, maxx, y_mid),
        (minx, y_mid, x_mid, maxy),
        (x_mid, y_mid, maxx, maxy),
    ]


def fetch_osm_tile(bounds, depth=0, max_depth=2):
    west, south, east, north = bounds
    query = (
        f'[out:json][timeout:120];'
        f'way["highway"]({south},{west},{north},{east});'
        f'out geom;'
    )

    try:
        return post_overpass(query).get("elements", [])
    except requests.HTTPError as error:
        status = getattr(error.response, "status_code", None)
        if status in {429, 504} and depth < max_depth:
            time.sleep(1.0 + depth)
            merged = {}
            for sub_bounds in subdivide_bounds(bounds):
                for element in fetch_osm_tile(sub_bounds, depth + 1, max_depth):
                    merged[element["id"]] = element
            return list(merged.values())
        raise


def fetch_osm_ways(bounds, use_cache=True):
    if use_cache and OSM_CACHE_PATH.exists():
        return load_geojson(OSM_CACHE_PATH)

    merged = {}
    for tile in subdivide_bounds(bounds):
        for element in fetch_osm_tile(tile, depth=0, max_depth=2):
            merged[element["id"]] = element

    payload = {"elements": list(merged.values())}
    save_json(OSM_CACHE_PATH, payload)
    return payload


def build_graph(overpass_json):
    graph = nx.Graph()

    for element in overpass_json.get("elements", []):
        if element.get("type") != "way":
            continue

        tags = element.get("tags", {})
        if not is_walkable(tags):
            continue

        geometry = element.get("geometry", [])
        if len(geometry) < 2:
            continue

        coords_utm = [transformer_to_utm.transform(item["lon"], item["lat"]) for item in geometry]
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

    return graph


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
    distances = {}
    heap = []

    for node in set(source_nodes):
        distances[node] = 0.0
        heap.append((0.0, node))

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

    for node_id in distances:
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
    return merged.buffer(30).buffer(-20)


def geometry_mapping(geom):
    simplified = geom.simplify(8, preserve_topology=True)
    if simplified.is_empty:
        simplified = geom.convex_hull
    if isinstance(simplified, Polygon):
        return mapping(simplified)
    if isinstance(simplified, MultiPolygon):
        return mapping(simplified)
    return mapping(simplified.convex_hull)

def build_area_feature(geometry, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry_mapping(to_wgs84(geometry)),
    }


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

    raw_sources = []
    for feature in equipamientos_data["features"]:
        geom = shape(feature["geometry"])
        point = geom.representative_point()
        equipamien = feature["properties"].get("equipamien") or feature["properties"].get("categoria") or ""
        platform_name = None
        for name in neighbor_names:
            if platform_geoms[name].contains(point) or platform_geoms[name].touches(point):
                platform_name = name
                break
        if not platform_name:
            continue

        raw_sources.append({
            "objectid": int(feature["properties"]["objectid"]),
            "nombre": feature["properties"]["nombre"],
            "equipamien": equipamien,
            "categoria": equipamien,
            "codigo": feature["properties"]["codigo"],
            "platform_name": platform_name,
            "point": point,
        })

    search_area = to_wgs84(to_utm(neighbor_union).buffer(BUFFER_METERS))
    overpass_json = fetch_osm_ways(search_area.bounds, use_cache=True)
    graph = build_graph(overpass_json)
    nodes = list(graph.nodes(data=True))

    snapped_sources = []
    for source in raw_sources:
        point_utm = to_utm(source["point"])
        node_id, snap_distance = nearest_node((point_utm.x, point_utm.y), nodes)
        if node_id is None:
            continue
        source["point_utm"] = point_utm
        source["node_id"] = node_id
        source["snap_m"] = snap_distance
        snapped_sources.append(source)

    by_platform_nodes = defaultdict(list)
    by_platform_types = defaultdict(Counter)

    for source in snapped_sources:
        by_platform_nodes[source["platform_name"]].append(source["node_id"])
        by_platform_types[source["platform_name"]][source["equipamien"]] += 1

    platform_features = []
    platform_stats = {}

    for platform_name in neighbor_names:
        node_ids = by_platform_nodes.get(platform_name, [])
        if not node_ids:
            continue

        reachable = multi_source_reachable(graph, node_ids, DISTANCE_METERS)
        if not reachable:
            continue

        polygon = build_isochrone_polygon(graph, reachable, DISTANCE_METERS)
        equipamien_counter = by_platform_types[platform_name]
        equipamientos_origen = sum(equipamien_counter.values())
        tipos_equipamien = len(equipamien_counter)
        equipamien_top = ", ".join(
            f"{label} ({count})"
            for label, count in equipamien_counter.most_common(4)
        )

        platform_features.append(
            build_area_feature(
                polygon,
                {
                    "platform_name": platform_name,
                    "target_platform": TARGET_PLATFORM,
                    "distance_m": DISTANCE_METERS,
                    "mode": "walking",
                    "equipamientos_origen": equipamientos_origen,
                    "tipos_equipamien": tipos_equipamien,
                    "equipamien_top": equipamien_top,
                    "nodos_alcanzables": len(reachable),
                },
            )
        )

        platform_stats[platform_name] = {
            "equipamientos_origen": equipamientos_origen,
            "tipos_equipamien": tipos_equipamien,
            "nodos_alcanzables": len(reachable),
            "equipamien": dict(
                sorted(equipamien_counter.items(), key=lambda item: (-item[1], item[0]))
            ),
        }

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "target_platform": TARGET_PLATFORM,
        "neighbor_platforms": neighbor_names,
        "equipamientos_origen": len(snapped_sources),
        "distance_m": DISTANCE_METERS,
        "mode": "walking",
        "plataformas_con_isocrona": len(platform_features),
        "source": "OpenStreetMap peatonal + equipamientos de plataformas colindantes",
        "by_platform": platform_stats,
    }

    save_json(OUTPUT_BY_PLATFORM, {"type": "FeatureCollection", "features": platform_features})
    with open(OUTPUT_STATS, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    print("Listo.")
    print(f"Vecinas: {neighbor_names}")
    print(f"Equipamientos origen: {len(snapped_sources)}")
    print(f"Isocronas por plataforma colindante: {len(platform_features)}")


if __name__ == "__main__":
    main()
