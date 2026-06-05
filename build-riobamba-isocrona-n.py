import heapq
import json
import math
import time
from pathlib import Path

import networkx as nx
import requests
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import linemerge, transform, unary_union
from shapely.strtree import STRtree


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
PLATFORMS_PATH = DATA_DIR / "riobamba_plataformas.geojson"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"
MANZANAS_STATS_PATH = DATA_DIR / "riobamba_manzanas_stats.json"
OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json"

OUTPUT_ISOCHRONE = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m.geojson"
OUTPUT_NETWORK = DATA_DIR / "riobamba_red_vial_isocrona_limite_plataforma_n_400m.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_stats.json"
OUTPUT_ISOCHRONE_CARTO = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_ajustada_manzanas.geojson"
OUTPUT_STATS_CARTO = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_ajustada_manzanas_stats.json"

TARGET_PLATFORM = "PLATAFORMA " + chr(209)
DISTANCE_METERS = 400
BUFFER_METERS = 1000
MANZANA_OVERLAP_RATIO_THRESHOLD = 0.25
MANZANA_REP_BUFFER_METERS = 20
CARTO_CLOSE_GAP_METERS = 10
CARTO_MIN_COMPONENT_AREA_M2 = 30000
CARTO_MIN_COMPONENT_RATIO = 0.01
BOUNDARY_SAMPLE_STEP_METERS = 20
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


def canonical_edge_key(start_node, end_node):
    return (start_node, end_node) if start_node <= end_node else (end_node, start_node)


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


def build_edge_index(graph):
    edge_geometries = []
    edge_metadata = []

    for start_node, end_node, attrs in graph.edges(data=True):
        edge_start, edge_end = canonical_edge_key(start_node, end_node)
        sx, sy = graph.nodes[edge_start]["x"], graph.nodes[edge_start]["y"]
        ex, ey = graph.nodes[edge_end]["x"], graph.nodes[edge_end]["y"]
        line = LineString([(sx, sy), (ex, ey)])
        if line.length <= 0:
            continue

        edge_geometries.append(line)
        edge_metadata.append({
            "edge_key": (edge_start, edge_end),
            "edge_length_m": line.length,
            "highway": attrs.get("highway", "road"),
        })

    return STRtree(edge_geometries), edge_geometries, edge_metadata


def nearest_edge_projection(point_xy, edge_tree, edge_geometries, edge_metadata):
    point = Point(*point_xy)
    nearest_index = edge_tree.nearest(point)
    if nearest_index is None:
        return None

    line = edge_geometries[int(nearest_index)]
    metadata = edge_metadata[int(nearest_index)]
    offset_m = line.project(point)
    projected_point = line.interpolate(offset_m)
    snap_m = point.distance(projected_point)

    return {
        "edge_key": metadata["edge_key"],
        "edge_length_m": metadata["edge_length_m"],
        "offset_m": offset_m,
        "projected_xy": (projected_point.x, projected_point.y),
        "highway": metadata["highway"],
        "snap_m": snap_m,
    }


def split_edges_with_projected_sources(graph, source_entries):
    augmented_graph = graph.copy()
    grouped_sources = {}

    for source in source_entries:
        grouped_sources.setdefault(source["edge_key"], []).append(source)

    for edge_key, edge_sources in grouped_sources.items():
        start_node, end_node = edge_key
        edge_attrs = graph.get_edge_data(start_node, end_node)
        if not edge_attrs:
            continue

        edge_length_m = float(edge_attrs.get("weight", 0.0))
        if edge_length_m <= 0:
            continue

        start_xy = (graph.nodes[start_node]["x"], graph.nodes[start_node]["y"])
        end_xy = (graph.nodes[end_node]["x"], graph.nodes[end_node]["y"])

        offset_node_map = {
            0.0: (start_node, start_xy),
            round(edge_length_m, 3): (end_node, end_xy),
        }

        for source in edge_sources:
            offset_m = max(0.0, min(edge_length_m, float(source["offset_m"])))
            rounded_offset = round(offset_m, 3)

            if rounded_offset in offset_node_map:
                node_id, projected_xy = offset_node_map[rounded_offset]
            else:
                node_id = ("src", source["source_id"])
                projected_xy = source["projected_xy"]
                offset_node_map[rounded_offset] = (node_id, projected_xy)
                augmented_graph.add_node(node_id, x=projected_xy[0], y=projected_xy[1], kind="boundary_source")

            source["node_id"] = node_id
            source["projected_xy"] = projected_xy

        if augmented_graph.has_edge(start_node, end_node):
            augmented_graph.remove_edge(start_node, end_node)

        sorted_offsets = sorted(offset_node_map.items(), key=lambda item: item[0])
        for (offset_a, (node_a, _)), (offset_b, (node_b, _)) in zip(sorted_offsets, sorted_offsets[1:]):
            segment_length = offset_b - offset_a
            if segment_length <= 0:
                continue
            augmented_graph.add_edge(
                node_a,
                node_b,
                weight=segment_length,
                highway=edge_attrs.get("highway", "road"),
            )

    return augmented_graph


def multi_source_reachable(graph, source_entries, cutoff):
    distances = {}
    heap = []

    for source in source_entries:
        node = source["node_id"]
        initial_distance = float(source.get("initial_distance_m", 0.0))
        if initial_distance > cutoff:
            continue
        if initial_distance < distances.get(node, float("inf")):
            distances[node] = initial_distance
            heap.append((initial_distance, node))

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


def sample_boundary_points(boundary_geom, step_m):
    lines = []
    if isinstance(boundary_geom, LineString):
        lines = [boundary_geom]
    elif isinstance(boundary_geom, MultiLineString):
        lines = list(boundary_geom.geoms)
    else:
        return []

    sampled_points = []
    for line in lines:
        if line.is_empty or line.length <= 0:
            continue

        distance = 0.0
        while distance < line.length:
            sampled_points.append(line.interpolate(distance))
            distance += step_m
        sampled_points.append(line.interpolate(line.length))

    return sampled_points


def align_polygon_to_manzanas(manzana_features, isochrone_polygon):
    selected_geometries = []
    selected_ids = []
    selection_buffer = isochrone_polygon.buffer(MANZANA_REP_BUFFER_METERS)

    for feature in manzana_features:
        manzana_id = feature.get("properties", {}).get("man")
        geometry = feature.get("geometry")
        if not geometry:
            continue

        manzana_geom = to_utm(shape(geometry))
        if manzana_geom.is_empty or not manzana_geom.intersects(isochrone_polygon):
            continue

        overlap_geom = manzana_geom.intersection(isochrone_polygon)
        if overlap_geom.is_empty:
            continue

        manzana_area = float(manzana_geom.area)
        overlap_ratio = (overlap_geom.area / manzana_area) if manzana_area > 0 else 0.0
        representative_inside = selection_buffer.contains(manzana_geom.representative_point())
        if not representative_inside and overlap_ratio < MANZANA_OVERLAP_RATIO_THRESHOLD:
            continue

        selected_geometries.append(manzana_geom)
        if manzana_id:
            selected_ids.append(manzana_id)

    if not selected_geometries:
        return isochrone_polygon, []

    return unary_union(selected_geometries), selected_ids


def build_external_limit_polygon(aligned_polygon, close_gap_m):
    # Close the internal road gaps so the final geometry draws as one outer silhouette.
    closed = aligned_polygon.buffer(close_gap_m).buffer(-close_gap_m)
    if closed.is_empty:
        return aligned_polygon
    return closed


def polygon_parts(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if not part.is_empty]
    return []


def remove_internal_holes(geometry):
    if isinstance(geometry, Polygon):
        return Polygon(geometry.exterior)
    if isinstance(geometry, MultiPolygon):
        polygons = [Polygon(part.exterior) for part in geometry.geoms if not part.is_empty]
        if not polygons:
            return geometry
        return unary_union(polygons)
    return geometry


def keep_significant_components(geometry, min_area_m2, min_area_ratio):
    parts = sorted(polygon_parts(geometry), key=lambda part: part.area, reverse=True)
    if not parts:
        return geometry

    largest_area = parts[0].area
    area_threshold = max(min_area_m2, largest_area * min_area_ratio)
    kept_parts = [parts[0]]
    kept_parts.extend(part for part in parts[1:] if part.area >= area_threshold)
    return unary_union(kept_parts)


def homogenize_cartographic_polygon(aligned_polygon):
    # Build a cleaner cartographic shell from the manzana-aligned geometry.
    closed = build_external_limit_polygon(aligned_polygon, CARTO_CLOSE_GAP_METERS)
    holeless = remove_internal_holes(closed)
    filtered = keep_significant_components(
        holeless,
        CARTO_MIN_COMPONENT_AREA_M2,
        CARTO_MIN_COMPONENT_RATIO,
    )
    cleaned = filtered.buffer(0)
    if cleaned.is_empty:
        return holeless
    return cleaned


def population_total_for_manzanas(selected_ids, manzana_stats_by_id):
    total = 0
    for manzana_id in selected_ids:
        stats = manzana_stats_by_id.get(manzana_id) or {}
        total += int(stats.get("population_total", 0) or 0)
    return total


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
    manzanas_data = load_geojson(MANZANAS_PATH)
    manzanas_stats = load_geojson(MANZANAS_STATS_PATH)
    manzana_stats_by_id = manzanas_stats.get("byMan", {})

    platform_geoms = {
        feature["properties"]["platform_name"]: shape(feature["geometry"])
        for feature in platforms_data["features"]
    }

    target_geom = platform_geoms[TARGET_PLATFORM]
    target_geom_utm = to_utm(target_geom)
    boundary_geom_utm = target_geom_utm.boundary
    sampled_boundary_points = sample_boundary_points(boundary_geom_utm, BOUNDARY_SAMPLE_STEP_METERS)

    search_area = to_wgs84(target_geom_utm.buffer(BUFFER_METERS))
    overpass_json = fetch_osm_ways(search_area.bounds, use_cache=True)
    base_graph = build_graph(overpass_json)
    edge_tree, edge_geometries, edge_metadata = build_edge_index(base_graph)

    projected_sources = []
    for index, point_utm in enumerate(sampled_boundary_points, start=1):
        projection = nearest_edge_projection((point_utm.x, point_utm.y), edge_tree, edge_geometries, edge_metadata)
        if projection is None:
            continue
        projected_sources.append({
            "source_id": index,
            "sample_point_utm": point_utm,
            "initial_distance_m": float(projection["snap_m"]),
            **projection,
        })

    graph = split_edges_with_projected_sources(base_graph, projected_sources)
    reachable = multi_source_reachable(graph, projected_sources, DISTANCE_METERS)
    segments, total_length = build_reachable_segments(graph, reachable, DISTANCE_METERS)
    source_points = [source["projected_xy"] for source in projected_sources]
    base_polygon = build_isochrone_polygon(segments, source_points)
    exact_polygon = base_polygon.buffer(0)
    if exact_polygon.is_empty:
        exact_polygon = base_polygon
    aligned_polygon, covered_manzanas = align_polygon_to_manzanas(manzanas_data["features"], exact_polygon)
    cartographic_polygon = homogenize_cartographic_polygon(aligned_polygon)
    population_total = population_total_for_manzanas(covered_manzanas, manzana_stats_by_id)

    network_geom = normalize_multilines(segments)
    source_node_count = len({source["node_id"] for source in projected_sources if source.get("node_id") is not None})
    snap_values = sorted(source["snap_m"] for source in projected_sources)
    average_snap_m = round(sum(snap_values) / len(snap_values), 2) if snap_values else 0.0
    p95_snap_m = round(snap_values[max(0, math.ceil(len(snap_values) * 0.95) - 1)], 2) if snap_values else 0.0
    max_snap_m = round(snap_values[-1], 2) if snap_values else 0.0

    polygon_feature = build_polygon_feature(
        exact_polygon,
        {
            "nombre": f"Isocrona exacta de red 400 m desde el borde de {TARGET_PLATFORM}",
            "target_platform": TARGET_PLATFORM,
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "source_type": "platform_boundary",
            "boundary_samples": len(sampled_boundary_points),
            "source_nodes": source_node_count,
            "snap_promedio_m": average_snap_m,
            "snap_p95_m": p95_snap_m,
            "snap_max_m": max_snap_m,
            "nodos_alcanzables": len(reachable),
            "longitud_red_m": round(total_length, 2),
            "population_total": population_total,
            "area_poligono_red_m2": round(exact_polygon.area, 2),
            "area_poligono_exacto_m2": round(exact_polygon.area, 2),
            "area_poligono_m2": round(exact_polygon.area, 2),
        },
    )

    cartographic_polygon_feature = build_polygon_feature(
        cartographic_polygon,
        {
            "nombre": f"Isocrona 400 m ajustada a manzanas desde el borde de {TARGET_PLATFORM}",
            "target_platform": TARGET_PLATFORM,
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "source_type": "platform_boundary_carto_reference",
            "boundary_samples": len(sampled_boundary_points),
            "source_nodes": source_node_count,
            "snap_promedio_m": average_snap_m,
            "snap_p95_m": p95_snap_m,
            "snap_max_m": max_snap_m,
            "nodos_alcanzables": len(reachable),
            "longitud_red_m": round(total_length, 2),
            "manzanas_ajustadas": len(covered_manzanas),
            "population_total": population_total,
            "area_poligono_red_m2": round(exact_polygon.area, 2),
            "area_poligono_manzanas_m2": round(aligned_polygon.area, 2),
            "area_poligono_m2": round(cartographic_polygon.area, 2),
            "reference_type": "manzana_aligned",
        },
    )

    network_feature = build_line_feature(
        network_geom,
        {
            "nombre": f"Red vial OSM alcanzable a {DISTANCE_METERS} m desde el borde de {TARGET_PLATFORM}",
            "target_platform": TARGET_PLATFORM,
            "distance_m": DISTANCE_METERS,
            "mode": "walking",
            "source_type": "platform_boundary",
            "boundary_samples": len(sampled_boundary_points),
            "source_nodes": source_node_count,
            "snap_promedio_m": average_snap_m,
            "snap_p95_m": p95_snap_m,
            "snap_max_m": max_snap_m,
            "segmentos_red": len(segments),
            "longitud_red_m": round(total_length, 2),
        },
    )

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "target_platform": TARGET_PLATFORM,
        "distance_m": DISTANCE_METERS,
        "mode": "walking",
        "source_type": "platform_boundary",
        "boundary_samples": len(sampled_boundary_points),
        "source_nodes": source_node_count,
        "snap_promedio_m": average_snap_m,
        "snap_p95_m": p95_snap_m,
        "snap_max_m": max_snap_m,
        "nodos_alcanzables": len(reachable),
        "segmentos_red": len(segments),
        "longitud_red_m": round(total_length, 2),
        "population_total": population_total,
        "area_poligono_red_m2": round(exact_polygon.area, 2),
        "area_poligono_exacto_m2": round(exact_polygon.area, 2),
        "area_poligono_m2": round(exact_polygon.area, 2),
        "source": "OpenStreetMap peatonal + proyeccion del borde de la plataforma a la red + descuento del acceso hasta la via + sin ajuste a manzanas censales",
    }

    stats_carto = {
        "generated_at": stats["generated_at"],
        "target_platform": TARGET_PLATFORM,
        "distance_m": DISTANCE_METERS,
        "mode": "walking",
        "source_type": "platform_boundary_carto_reference",
        "boundary_samples": len(sampled_boundary_points),
        "source_nodes": source_node_count,
        "snap_promedio_m": average_snap_m,
        "snap_p95_m": p95_snap_m,
        "snap_max_m": max_snap_m,
        "nodos_alcanzables": len(reachable),
        "segmentos_red": len(segments),
        "longitud_red_m": round(total_length, 2),
        "manzanas_ajustadas": len(covered_manzanas),
        "population_total": population_total,
        "area_poligono_red_m2": round(exact_polygon.area, 2),
        "area_poligono_manzanas_m2": round(aligned_polygon.area, 2),
        "area_poligono_m2": round(cartographic_polygon.area, 2),
        "source": "OpenStreetMap peatonal + proyeccion del borde de la plataforma a la red + descuento del acceso hasta la via + ajuste del limite a manzanas censales",
        "reference_type": "manzana_aligned",
    }

    save_json(OUTPUT_ISOCHRONE, {"type": "FeatureCollection", "features": [polygon_feature]})
    save_json(OUTPUT_NETWORK, {"type": "FeatureCollection", "features": [network_feature]})
    save_json(OUTPUT_STATS, stats)
    save_json(OUTPUT_ISOCHRONE_CARTO, {"type": "FeatureCollection", "features": [cartographic_polygon_feature]})
    save_json(OUTPUT_STATS_CARTO, stats_carto)

    print("Listo.")
    print(f"Muestras del limite de {TARGET_PLATFORM}: {len(sampled_boundary_points)}")
    print(f"Nodos origen sobre red: {source_node_count}")
    print(f"Snap promedio al eje vial: {average_snap_m} m")
    print(f"Snap p95 al eje vial: {p95_snap_m} m")
    print(f"Snap maximo al eje vial: {max_snap_m} m")
    print(f"Nodos alcanzables: {len(reachable)}")
    print(f"Segmentos de red: {len(segments)}")
    print(f"Longitud total de red: {round(total_length, 2)} m")
    print(f"Area exacta de red: {round(exact_polygon.area, 2)} m2")
    print(f"Area cartografica ajustada: {round(cartographic_polygon.area, 2)} m2")


if __name__ == "__main__":
    main()
