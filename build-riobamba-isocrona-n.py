import heapq
import json
import math
import time
from collections import Counter
from pathlib import Path

import networkx as nx
import requests
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import linemerge, transform, unary_union


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
PLATFORMS_PATH = DATA_DIR / "riobamba_plataformas.geojson"
EQUIPAMIENTOS_PATH = DATA_DIR / "riobamba_equipamientos.geojson"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"
OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json"

OUTPUT_ISOCHRONE = DATA_DIR / "riobamba_isocrona_plataforma_n_1000m.geojson"
OUTPUT_NETWORK = DATA_DIR / "riobamba_red_vial_isocrona_plataforma_n_1000m.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba_isocrona_plataforma_n_1000m_stats.json"

TARGET_PLATFORM = "PLATAFORMA " + chr(209)
DISTANCE_METERS = 1000
BUFFER_METERS = 1500
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


def save_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


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
            "User-Agent": "codex-riobamba-isochrone/2.0",
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
            graph.add_edge(start_id, end_id, weight=length, highway=tags.get("highway", "road"))

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


def build_reachable_segments(graph, distances, cutoff):
    segments = []
    total_length = 0.0

    for start, end, attrs in graph.edges(data=True):
        d1 = distances.get(start)
        d2 = distances.get(end)
        if d1 is None and d2 is None:
            continue

        sx, sy = graph.nodes[start]["x"], graph.nodes[start]["y"]
        ex, ey = graph.nodes[end]["x"], graph.nodes[end]["y"]
        length = float(attrs.get("weight", 0.0))
        if length <= 0:
            continue

        if d1 is not None and d2 is not None:
            segment = LineString([(sx, sy), (ex, ey)])
        else:
            known_dist = d1 if d1 is not None else d2
            remaining = cutoff - known_dist
            if remaining <= 0:
                continue
            ratio = min(1.0, remaining / length)
            if d1 is not None:
                mx = sx + (ex - sx) * ratio
                my = sy + (ey - sy) * ratio
                segment = LineString([(sx, sy), (mx, my)])
            else:
                mx = ex + (sx - ex) * ratio
                my = ey + (sy - ey) * ratio
                segment = LineString([(ex, ey), (mx, my)])

        if segment.length <= 0:
            continue
        segments.append(segment)
        total_length += segment.length

    return segments, total_length


def build_isochrone_polygon(segments, source_points):
    node_buffers = [Point(x, y).buffer(18) for x, y in source_points]
    edge_buffers = [segment.buffer(14) for segment in segments]
    merged = unary_union(node_buffers + edge_buffers)
    polygon = merged.buffer(12).buffer(-8)
    if polygon.is_empty:
        polygon = merged.convex_hull
    return polygon


def align_polygon_to_manzanas(manzana_features, isochrone_polygon):
    selected_geometries = []
    selected_ids = []

    for feature in manzana_features:
        manzana_id = feature.get("properties", {}).get("man")
        geometry = feature.get("geometry")
        if not geometry:
            continue

        manzana_geom = to_utm(shape(geometry))
        if manzana_geom.is_empty or not manzana_geom.intersects(isochrone_polygon):
            continue

        selected_geometries.append(manzana_geom)
        if manzana_id:
            selected_ids.append(manzana_id)

    if not selected_geometries:
        return isochrone_polygon, []

    return unary_union(selected_geometries), selected_ids


def geometry_mapping(geom):
    if isinstance(geom, (Polygon, MultiPolygon)):
        cleaned = geom.buffer(0)
        if cleaned.is_empty:
            cleaned = geom
        return mapping(cleaned)
    return mapping(geom)


def build_polygon_feature(geometry, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry_mapping(to_wgs84(geometry)),
    }


def build_line_feature(geometry, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": mapping(to_wgs84(geometry)),
    }


def normalize_multilines(segments):
    if not segments:
        return MultiLineString([])
    merged = unary_union(segments)
    if isinstance(merged, LineString):
        return MultiLineString([merged])
    if isinstance(merged, MultiLineString):
        return merged
    line_merged = linemerge(merged)
    if isinstance(line_merged, LineString):
        return MultiLineString([line_merged])
    if isinstance(line_merged, MultiLineString):
        return line_merged
    return MultiLineString([])


def main():
    platforms_data = load_geojson(PLATFORMS_PATH)
    equipamientos_data = load_geojson(EQUIPAMIENTOS_PATH)
    manzanas_data = load_geojson(MANZANAS_PATH)

    platform_geoms = {
        feature["properties"]["platform_name"]: shape(feature["geometry"])
        for feature in platforms_data["features"]
    }

    target_geom = platform_geoms[TARGET_PLATFORM]
    target_geom_utm = to_utm(target_geom)

    source_equipamientos = []
    equipamien_counter = Counter()
    for feature in equipamientos_data["features"]:
        geom = shape(feature["geometry"])
        point = geom.representative_point()
        if not (target_geom.contains(point) or target_geom.touches(point)):
            continue

        equipamien = feature["properties"].get("equipamien") or feature["properties"].get("categoria") or "Sin clasificar"
        equipamien_counter[equipamien] += 1
        source_equipamientos.append({
            "objectid": int(feature["properties"].get("objectid", 0) or 0),
            "nombre": feature["properties"].get("nombre", ""),
            "equipamien": equipamien,
            "codigo": feature["properties"].get("codigo", ""),
            "point": point,
        })

    search_area = to_wgs84(target_geom_utm.buffer(BUFFER_METERS))
    overpass_json = fetch_osm_ways(search_area.bounds, use_cache=True)
    graph = build_graph(overpass_json)
    nodes = list(graph.nodes(data=True))

    snapped_sources = []
    for source in source_equipamientos:
        point_utm = to_utm(source["point"])
        node_id, snap_distance = nearest_node((point_utm.x, point_utm.y), nodes)
        if node_id is None:
            continue
        source["point_utm"] = point_utm
        source["node_id"] = node_id
        source["snap_m"] = snap_distance
        snapped_sources.append(source)

    reachable = multi_source_reachable(graph, [source["node_id"] for source in snapped_sources], DISTANCE_METERS)
    segments, total_length = build_reachable_segments(graph, reachable, DISTANCE_METERS)
    source_points = [(source["point_utm"].x, source["point_utm"].y) for source in snapped_sources]
    base_polygon = build_isochrone_polygon(segments, source_points)
    polygon, covered_manzanas = align_polygon_to_manzanas(manzanas_data["features"], base_polygon)

    network_geom = normalize_multilines(segments)

    polygon_feature = build_polygon_feature(
        polygon,
        {
            "nombre": f"Isocrona 1000 m ajustada a manzanas desde equipamientos de {TARGET_PLATFORM}",
            "target_platform": TARGET_PLATFORM,
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "equipamientos_origen": len(snapped_sources),
            "tipos_equipamien": len(equipamien_counter),
            "nodos_alcanzables": len(reachable),
            "longitud_red_m": round(total_length, 2),
            "manzanas_ajustadas": len(covered_manzanas),
            "area_poligono_red_m2": round(base_polygon.area, 2),
            "area_poligono_m2": round(polygon.area, 2),
        },
    )

    network_feature = build_line_feature(
        network_geom,
        {
            "nombre": f"Red vial OSM alcanzable a {DISTANCE_METERS} m desde equipamientos de {TARGET_PLATFORM}",
            "target_platform": TARGET_PLATFORM,
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "equipamientos_origen": len(snapped_sources),
            "segmentos_red": len(segments),
            "longitud_red_m": round(total_length, 2),
        },
    )

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "target_platform": TARGET_PLATFORM,
        "distance_m": DISTANCE_METERS,
        "mode": "walking",
        "equipamientos_origen": len(snapped_sources),
        "tipos_equipamien": len(equipamien_counter),
        "nodos_alcanzables": len(reachable),
        "segmentos_red": len(segments),
        "longitud_red_m": round(total_length, 2),
        "manzanas_ajustadas": len(covered_manzanas),
        "area_poligono_red_m2": round(base_polygon.area, 2),
        "area_poligono_m2": round(polygon.area, 2),
        "source": "OpenStreetMap peatonal + equipamientos dentro de la plataforma objetivo + ajuste del limite a manzanas censales",
        "by_equipamien": dict(sorted(equipamien_counter.items(), key=lambda item: (-item[1], item[0]))),
    }

    save_json(OUTPUT_ISOCHRONE, {"type": "FeatureCollection", "features": [polygon_feature]})
    save_json(OUTPUT_NETWORK, {"type": "FeatureCollection", "features": [network_feature]})
    save_json(OUTPUT_STATS, stats)

    print("Listo.")
    print(f"Equipamientos origen en {TARGET_PLATFORM}: {len(snapped_sources)}")
    print(f"Nodos alcanzables: {len(reachable)}")
    print(f"Segmentos de red: {len(segments)}")
    print(f"Longitud total de red: {round(total_length, 2)} m")


if __name__ == "__main__":
    main()
