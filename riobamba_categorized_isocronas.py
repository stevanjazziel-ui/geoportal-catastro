import argparse
import collections
import heapq
import json
import math
import subprocess
import shutil
import sys
import zipfile
from dataclasses import replace

import networkx as nx
import shapefile
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from riobamba_categorized_isocronas_config import (
    BASE_DIR,
    DATA_DIR,
    CATEGORIZED_ISOCHRONE_CONFIGS,
    CategorizedIsochroneConfig,
    get_categorized_isochrone_config,
    iter_categorized_isochrone_configs,
)


OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"
MANZANAS_STATS_PATH = DATA_DIR / "riobamba_manzanas_stats.json"

MANZANA_OVERLAP_RATIO_THRESHOLD = 0.25
MANZANA_REP_BUFFER_METERS = 20
EXTERNAL_CLOSE_GAP_METERS = 10
HOMOGENIZE_MAX_EXPANSION_METERS = 12
FINAL_EXACT_CLIP_BUFFER_METERS = 18
MIN_COMPONENT_AREA_M2 = 1200
MIN_COMPONENT_RATIO = 0.04
LARGE_MANZANA_AREA_THRESHOLD_M2 = 20000
LARGE_MANZANA_FRONTAGE_LENGTH_M = 200
LARGE_MANZANA_MIN_OVERLAP_AREA_M2 = 1500
NETWORK_FRONTAGE_BUFFER_METERS = 20
NETWORK_FRONTAGE_LENGTH_M = 30
NETWORK_FRONTAGE_MIN_OVERLAP_AREA_M2 = 100
NETWORK_FRONTAGE_MIN_OVERLAP_RATIO = 0.02
MAX_VERTEX_TOLERANCE_BY_DISTANCE = {
    400: 60,
    1000: 100,
}

WALKABLE_HIGHWAYS = {
    "footway",
    "path",
    "pedestrian",
    "living_street",
    "residential",
    "service",
    "tertiary",
    "tertiary_link",
    "secondary",
    "secondary_link",
    "primary",
    "primary_link",
    "unclassified",
    "track",
    "cycleway",
    "steps",
}
BLOCKED_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed"}

transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True)
transformer_to_wgs = Transformer.from_crs("EPSG:32717", "EPSG:4326", always_xy=True)


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        if str(path).lower().endswith(".geojson"):
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, handle, ensure_ascii=False, indent=2)


def to_utm(geom):
    return transform(transformer_to_utm.transform, geom)


def to_wgs84(geom):
    return transform(transformer_to_wgs.transform, geom)


def geometry_mapping(geom):
    if isinstance(geom, (Polygon, MultiPolygon)):
        cleaned = geom.buffer(0)
        return mapping(cleaned if not cleaned.is_empty else geom)
    return mapping(geom)


def normalize_text(value):
    return str(value or "").strip()


def first_present(record, candidates):
    for candidate in candidates:
        value = record.get(candidate)
        if value not in (None, ""):
            return value
    return ""


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
        for index in range(len(coords_utm) - 1):
            start = coords_utm[index]
            end = coords_utm[index + 1]
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
        edge_metadata.append(
            {
                "edge_key": (edge_start, edge_end),
                "edge_length_m": line.length,
                "highway": attrs.get("highway", "road"),
            }
        )

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
                augmented_graph.add_node(node_id, x=projected_xy[0], y=projected_xy[1], kind="source")

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
            heapq.heappush(heap, (initial_distance, node))

    while heap:
        current_distance, node = heapq.heappop(heap)
        if current_distance > distances.get(node, float("inf")):
            continue
        if current_distance > cutoff:
            continue

        for neighbor, attrs in graph[node].items():
            step = float(attrs.get("weight", 0.0))
            if step <= 0:
                continue
            next_distance = current_distance + step
            if next_distance > cutoff:
                continue
            if next_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = next_distance
                heapq.heappush(heap, (next_distance, neighbor))

    return distances


def build_reachable_segments(graph, reachable, cutoff):
    seen_edges = set()
    segments = []
    total_length = 0.0

    for start_node, start_distance in reachable.items():
        for end_node, attrs in graph[start_node].items():
            edge_key = canonical_edge_key(start_node, end_node)
            if edge_key in seen_edges:
                continue

            weight = float(attrs.get("weight", 0.0))
            if weight <= 0:
                continue

            end_distance = reachable.get(end_node)
            reachable_length = 0.0
            if end_distance is not None:
                if start_distance <= cutoff or end_distance <= cutoff:
                    reachable_length = weight
            elif start_distance < cutoff:
                reachable_length = min(weight, cutoff - start_distance)

            if reachable_length <= 0:
                continue

            seen_edges.add(edge_key)

            sx, sy = graph.nodes[start_node]["x"], graph.nodes[start_node]["y"]
            ex, ey = graph.nodes[end_node]["x"], graph.nodes[end_node]["y"]
            line = LineString([(sx, sy), (ex, ey)])
            if reachable_length < weight:
                line = LineString([line.coords[0], line.interpolate(reachable_length).coords[0]])

            if line.length <= 0:
                continue

            segments.append(line)
            total_length += line.length

    return segments, total_length


def build_isochrone_polygon(segments, source_points):
    node_buffers = [Point(x, y).buffer(18) for x, y in source_points]
    edge_buffers = [segment.buffer(14) for segment in segments]
    merged = unary_union(node_buffers + edge_buffers)
    polygon = merged.buffer(12).buffer(-8)
    if polygon.is_empty:
        polygon = merged.convex_hull
    return polygon.buffer(0)


def polygon_parts(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if not part.is_empty]
    return []


def max_distance_to_geometry_boundary(geometry, source_point):
    max_distance = 0.0
    for part in polygon_parts(geometry):
        for x, y in part.exterior.coords:
            distance = source_point.distance(Point(x, y))
            if distance > max_distance:
                max_distance = distance
    return max_distance


def qualifies_large_manzana_frontage(manzana_geom, isochrone_polygon, overlap_geom):
    manzana_area = float(manzana_geom.area)
    if manzana_area < LARGE_MANZANA_AREA_THRESHOLD_M2:
        return False

    if overlap_geom.is_empty or overlap_geom.area < LARGE_MANZANA_MIN_OVERLAP_AREA_M2:
        return False

    frontage_length = manzana_geom.boundary.intersection(isochrone_polygon).length
    return frontage_length >= LARGE_MANZANA_FRONTAGE_LENGTH_M


def qualifies_network_frontage(manzana_geom, overlap_geom, overlap_ratio, reachable_corridor):
    if reachable_corridor is None:
        return False

    if overlap_geom.is_empty or overlap_geom.area < NETWORK_FRONTAGE_MIN_OVERLAP_AREA_M2:
        return False

    if overlap_ratio < NETWORK_FRONTAGE_MIN_OVERLAP_RATIO:
        return False

    frontage_length = manzana_geom.boundary.intersection(reachable_corridor).length
    return frontage_length >= NETWORK_FRONTAGE_LENGTH_M


def qualifies_special_manzana_tolerance(manzana_id, manzana_geom, isochrone_polygon, reachable_corridor, special_tolerance_rules):
    if not special_tolerance_rules:
        return False

    rule = special_tolerance_rules.get(str(manzana_id or ""))
    if not rule:
        return False

    max_polygon_distance = float(rule.get("max_polygon_distance_m", 0) or 0)
    if max_polygon_distance <= 0:
        return False

    if manzana_geom.distance(isochrone_polygon) > max_polygon_distance:
        return False

    max_corridor_distance = float(rule.get("max_corridor_distance_m", 0) or 0)
    if max_corridor_distance > 0:
        if reachable_corridor is None or manzana_geom.distance(reachable_corridor) > max_corridor_distance:
            return False

    return True


def clip_large_manzana_geometry(manzana_geom, overlap_geom):
    manzana_area = float(manzana_geom.area)
    if manzana_area < LARGE_MANZANA_AREA_THRESHOLD_M2:
        return manzana_geom, False

    if overlap_geom.is_empty:
        return manzana_geom, False

    clipped = overlap_geom.buffer(0)
    if clipped.is_empty:
        return manzana_geom, False

    if abs(float(clipped.area) - manzana_area) <= 1.0:
        return manzana_geom, False

    return clipped, True


def align_polygon_to_manzanas(
    manzana_features,
    isochrone_polygon,
    source_point,
    target_distance_m,
    reachable_segments=None,
    special_tolerance_rules=None,
):
    selected_geometries = []
    selected_ids = []
    clipped_large_ids = []
    selection_buffer = isochrone_polygon.buffer(MANZANA_REP_BUFFER_METERS)
    reachable_corridor = unary_union(reachable_segments).buffer(NETWORK_FRONTAGE_BUFFER_METERS) if reachable_segments else None
    max_vertex_distance = target_distance_m + MAX_VERTEX_TOLERANCE_BY_DISTANCE.get(
        int(target_distance_m),
        max(50, round(target_distance_m * 0.1)),
    )

    for feature in manzana_features:
        manzana_id = feature.get("properties", {}).get("man")
        geometry = feature.get("geometry")
        if not geometry:
            continue

        manzana_geom = to_utm(shape(geometry))
        if manzana_geom.is_empty:
            continue

        special_tolerance = qualifies_special_manzana_tolerance(
            manzana_id,
            manzana_geom,
            isochrone_polygon,
            reachable_corridor,
            special_tolerance_rules,
        )
        if not special_tolerance and not manzana_geom.intersects(isochrone_polygon):
            continue

        overlap_geom = manzana_geom.intersection(isochrone_polygon)
        if overlap_geom.is_empty and not special_tolerance:
            continue

        manzana_area = float(manzana_geom.area)
        overlap_ratio = (overlap_geom.area / manzana_area) if manzana_area > 0 else 0.0
        representative_inside = selection_buffer.contains(manzana_geom.representative_point())
        large_manzana_frontage = qualifies_large_manzana_frontage(
            manzana_geom,
            isochrone_polygon,
            overlap_geom,
        )
        network_frontage = qualifies_network_frontage(
            manzana_geom,
            overlap_geom,
            overlap_ratio,
            reachable_corridor,
        )
        if (
            not representative_inside
            and overlap_ratio < MANZANA_OVERLAP_RATIO_THRESHOLD
            and not large_manzana_frontage
            and not network_frontage
            and not special_tolerance
        ):
            continue
        if (
            not large_manzana_frontage
            and not network_frontage
            and not special_tolerance
            and max_distance_to_geometry_boundary(manzana_geom, source_point) > max_vertex_distance
        ):
            continue

        geometry_to_add, was_clipped = clip_large_manzana_geometry(
            manzana_geom,
            overlap_geom,
        )
        selected_geometries.append(geometry_to_add)
        if manzana_id:
            selected_ids.append(manzana_id)
            if was_clipped:
                clipped_large_ids.append(manzana_id)

    if not selected_geometries:
        return isochrone_polygon, [], []

    return unary_union(selected_geometries), selected_ids, clipped_large_ids


def build_external_limit_polygon(aligned_polygon, close_gap_m):
    closed = aligned_polygon.buffer(close_gap_m).buffer(-close_gap_m)
    if closed.is_empty:
        return aligned_polygon
    return closed


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


def homogenize_aligned_polygon(aligned_polygon):
    closed = build_external_limit_polygon(aligned_polygon, EXTERNAL_CLOSE_GAP_METERS)
    holeless = remove_internal_holes(closed)
    constrained = holeless.intersection(aligned_polygon.buffer(HOMOGENIZE_MAX_EXPANSION_METERS))
    if constrained.is_empty:
        constrained = holeless
    constrained_holeless = remove_internal_holes(constrained)
    filtered = keep_significant_components(
        constrained_holeless,
        MIN_COMPONENT_AREA_M2,
        MIN_COMPONENT_RATIO,
    )
    cleaned = filtered.buffer(0)
    if cleaned.is_empty:
        return constrained_holeless
    return cleaned


def clip_polygon_to_exact_limit(final_polygon, exact_polygon):
    clipped = final_polygon.intersection(exact_polygon.buffer(FINAL_EXACT_CLIP_BUFFER_METERS))
    if clipped.is_empty:
        return final_polygon
    cleaned = clipped.buffer(0)
    if cleaned.is_empty:
        return clipped
    return cleaned


def population_total_for_manzanas(selected_ids, manzana_stats_by_id):
    total = 0
    for manzana_id in selected_ids:
        stats = manzana_stats_by_id.get(manzana_id) or {}
        total += int(stats.get("population_total", 0) or 0)
    return total


def build_polygon_feature(geometry, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry_mapping(to_wgs84(geometry)),
    }


def build_source_feature(geometry_utm, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry_mapping(to_wgs84(geometry_utm)),
    }


def extract_archive(source_archive, extract_dir):
    suffix = source_archive.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(source_archive) as archive:
            archive.extractall(extract_dir)
        return
    if suffix == ".rar":
        subprocess.run(["tar", "-xf", str(source_archive), "-C", str(extract_dir)], check=True)
        return
    raise ValueError(f"Formato no soportado para {source_archive.name}. Usa ZIP o RAR.")


def extract_source_records(config):
    source_archive = config.resolve_source_zip()
    if not source_archive.exists():
        candidates = ", ".join(str(path) for path in config.source_zip_candidates)
        raise FileNotFoundError(f"No se encontro el archivo fuente para {config.display_name}. Revise: {candidates}")

    if config.extract_dir.exists():
        shutil.rmtree(config.extract_dir)
    config.extract_dir.mkdir(parents=True, exist_ok=True)

    extract_archive(source_archive, config.extract_dir)

    shp_path = next(config.extract_dir.rglob("*.shp"), None)
    if shp_path is None:
        raise FileNotFoundError(f"No se encontro un shapefile dentro del archivo fuente de {config.display_name}.")

    reader = shapefile.Reader(str(shp_path))
    try:
        records = []
        features = []
        category_counter = collections.Counter()

        for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = shape_record.record.as_dict()
            geometry_utm = shape(shape_record.shape.__geo_interface__)
            categoria = normalize_text(first_present(record, config.category_field_candidates)).upper()
            nombre = normalize_text(first_present(record, config.name_field_candidates))
            equipamien = normalize_text(first_present(record, config.type_field_candidates))
            codigo = normalize_text(first_present(record, config.code_field_candidates))
            distance_m = config.distance_by_category.get(categoria)

            category_counter[categoria or "SIN_CATEGORIA"] += 1

            properties = {
                "source_id": index,
                "objectid": int(record.get("OBJECTID", 0) or 0),
                "codigo": codigo,
                "equipamien": equipamien,
                "nombre": nombre,
                "categoria": categoria,
                "isocrona_distance_m": distance_m or 0,
                "genera_isocrona": bool(distance_m),
                "shape_area": float(record.get("Shape_Area", 0) or 0),
                "shape_leng": float(record.get("Shape_Leng", 0) or 0),
            }

            records.append(
                {
                    "properties": properties,
                    "geometry_utm": geometry_utm,
                }
            )
            features.append(build_source_feature(geometry_utm, properties))
    finally:
        reader.close()
        shutil.rmtree(config.extract_dir, ignore_errors=True)

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_archive": str(source_archive),
        "source_zip": str(source_archive),
        "summary": {
            "total_equipamientos": len(records),
            "con_isocrona": sum(1 for item in records if item["properties"]["genera_isocrona"]),
            "sin_isocrona": sum(1 for item in records if not item["properties"]["genera_isocrona"]),
            "categorias": len(category_counter),
        },
        "by_categoria": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
    }

    return records, {"type": "FeatureCollection", "features": features}, stats


def build_single_isochrone(config, record, manzana_features, manzana_stats_by_id, base_graph, edge_tree, edge_geometries, edge_metadata):
    props = record["properties"]
    geometry_utm = record["geometry_utm"]
    distance_m = int(props["isocrona_distance_m"])
    representative_point = geometry_utm.representative_point()

    projection = nearest_edge_projection(
        (representative_point.x, representative_point.y),
        edge_tree,
        edge_geometries,
        edge_metadata,
    )
    if projection is None:
        return None

    source_entry = {
        "source_id": props["source_id"],
        "initial_distance_m": float(projection["snap_m"]),
        **projection,
    }
    source_lon, source_lat = transformer_to_wgs.transform(*source_entry["projected_xy"])
    equip_lon, equip_lat = transformer_to_wgs.transform(representative_point.x, representative_point.y)

    graph = split_edges_with_projected_sources(base_graph, [source_entry])
    reachable = multi_source_reachable(graph, [source_entry], distance_m)
    segments, total_length = build_reachable_segments(graph, reachable, distance_m)

    if not segments:
        return None

    exact_polygon = build_isochrone_polygon(segments, [source_entry["projected_xy"]])
    if exact_polygon.is_empty:
        return None

    source_point = Point(*source_entry["projected_xy"])
    aligned_polygon, covered_manzanas, clipped_large_manzanas = align_polygon_to_manzanas(
        manzana_features,
        exact_polygon,
        source_point,
        distance_m,
        reachable_segments=segments,
    )
    final_polygon = homogenize_aligned_polygon(aligned_polygon)
    if final_polygon.is_empty:
        final_polygon = remove_internal_holes(aligned_polygon.buffer(0))
    if final_polygon.is_empty:
        final_polygon = exact_polygon
    final_polygon = clip_polygon_to_exact_limit(final_polygon, exact_polygon)
    final_polygon = remove_internal_holes(final_polygon)

    population_total = population_total_for_manzanas(covered_manzanas, manzana_stats_by_id)

    return build_polygon_feature(
        final_polygon,
        {
            "source_id": props["source_id"],
            "objectid": props["objectid"],
            "codigo": props["codigo"],
            "equipamien": props["equipamien"],
            "nombre": props["nombre"],
            "categoria": props["categoria"],
            "distance_m": distance_m,
            "mode": "walking",
            "origin_type": "equipamiento",
            "source_type": "equipamiento_manzana_aligned_external",
            "snap_m": round(float(projection["snap_m"]), 2),
            "source_node_id": str(source_entry.get("node_id")),
            "source_lon": round(source_lon, 8),
            "source_lat": round(source_lat, 8),
            "equipamiento_lon": round(equip_lon, 8),
            "equipamiento_lat": round(equip_lat, 8),
            "nodos_alcanzables": len(reachable),
            "segmentos_red": len(segments),
            "longitud_red_m": round(total_length, 2),
            "manzanas_ajustadas": len(covered_manzanas),
            "manzanas_grandes_recortadas": len(clipped_large_manzanas),
            "covered_manzanas": list(covered_manzanas),
            "clipped_large_manzanas": list(clipped_large_manzanas),
            "population_total": population_total,
            "area_poligono_red_m2": round(exact_polygon.area, 2),
            "area_poligono_manzanas_m2": round(aligned_polygon.area, 2),
            "area_poligono_m2": round(final_polygon.area, 2),
            "representation": "manzana_aligned_external_boundary",
        },
    )


def ensure_cache_covers_sources(records, osm_payload, display_name):
    min_lon = float("inf")
    min_lat = float("inf")
    max_lon = float("-inf")
    max_lat = float("-inf")

    for element in osm_payload.get("elements", []):
        for item in element.get("geometry", []):
            min_lon = min(min_lon, item["lon"])
            min_lat = min(min_lat, item["lat"])
            max_lon = max(max_lon, item["lon"])
            max_lat = max(max_lat, item["lat"])

    for record in records:
        point = to_wgs84(record["geometry_utm"].representative_point())
        if not (min_lon <= point.x <= max_lon and min_lat <= point.y <= max_lat):
            raise RuntimeError(
                f"La red OSM cacheada no cubre todos los equipamientos de {display_name}. "
                "Se necesita regenerar una cache mas amplia."
            )


def run_config(config):
    records, equipamientos_geojson, equipamientos_stats = extract_source_records(config)
    save_json(config.output_equipamientos, equipamientos_geojson)
    save_json(config.output_equipamientos_stats, equipamientos_stats)

    manzanas_data = load_json(MANZANAS_PATH)
    manzanas_stats = load_json(MANZANAS_STATS_PATH)
    manzana_stats_by_id = manzanas_stats.get("byMan", {})
    osm_payload = load_json(OSM_CACHE_PATH)
    ensure_cache_covers_sources(records, osm_payload, config.display_name)
    base_graph = build_graph(osm_payload)
    edge_tree, edge_geometries, edge_metadata = build_edge_index(base_graph)

    isocronas = []
    generated_counter = collections.Counter()
    skipped_counter = collections.Counter()

    for record in records:
        categoria = record["properties"]["categoria"] or "SIN_CATEGORIA"
        if not record["properties"]["genera_isocrona"]:
            skipped_counter[categoria] += 1
            continue

        feature = build_single_isochrone(
            config,
            record,
            manzanas_data["features"],
            manzana_stats_by_id,
            base_graph,
            edge_tree,
            edge_geometries,
            edge_metadata,
        )
        if feature is None:
            skipped_counter[f"{categoria}_SIN_RED"] += 1
            continue

        isocronas.append(feature)
        generated_counter[categoria] += 1

    isocronas.sort(
        key=lambda feature: (
            feature["properties"].get("distance_m", 0),
            feature["properties"].get("categoria", ""),
            feature["properties"].get("nombre", ""),
        )
    )

    output_geojson = {"type": "FeatureCollection", "features": isocronas}
    distance_breakdown = collections.Counter(
        int(feature["properties"].get("distance_m", 0) or 0)
        for feature in isocronas
        if int(feature["properties"].get("distance_m", 0) or 0) > 0
    )

    barrial_distance = config.distance_by_category.get("BARRIAL")
    zonal_distance = config.distance_by_category.get("ZONAL")
    barrial_text = f"{barrial_distance} m" if barrial_distance else "sin isocrona"
    zonal_text = f"{zonal_distance} m" if zonal_distance else "sin isocrona"

    output_stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_archive": str(config.resolve_source_zip()),
        "source_zip": str(config.resolve_source_zip()),
        "source_osm_cache": str(OSM_CACHE_PATH),
        "summary": {
            "total_equipamientos": len(records),
            "total_isocronas": len(isocronas),
            "categorias_con_isocrona": len(generated_counter),
            "omitidos": sum(skipped_counter.values()),
            "manzanas_ajustadas": sum(int(feature["properties"].get("manzanas_ajustadas", 0) or 0) for feature in isocronas),
            "manzanas_grandes_recortadas": sum(
                int(feature["properties"].get("manzanas_grandes_recortadas", 0) or 0)
                for feature in isocronas
            ),
        },
        "by_categoria_source": equipamientos_stats["by_categoria"],
        "by_categoria_isocronas": dict(sorted(generated_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_categoria_omitidos": dict(sorted(skipped_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_distance_m": dict(sorted((str(distance), count) for distance, count in distance_breakdown.items())),
        "observacion": (
            f"Se generan isocronas de {config.display_name} para BARRIAL ({barrial_text}) y "
            f"ZONAL ({zonal_text}). Los registros CANTONAL no se procesan. El resultado final "
            "queda ajustado a manzanas censales; cuando una manzana es grande se recorta al "
            "limite exacto de red para no extender la cobertura mas alla de la distancia "
            "objetivo. El resultado final queda sin huecos internos y preparado para mostrar "
            "solo el limite exterior."
        ),
    }

    save_json(config.output_isocronas, output_geojson)
    save_json(config.output_isocronas_stats, output_stats)

    print("Listo.")
    print(f"Equipamientos {config.display_name}: {config.output_equipamientos}")
    print(f"Stats {config.display_name}:         {config.output_equipamientos_stats}")
    print(f"Isocronas {config.display_name}:     {config.output_isocronas}")
    print(f"Stats iso {config.display_name}:     {config.output_isocronas_stats}")
    print(f"Total isocronas generadas: {len(isocronas)}")


def build_variant_config(
    config,
    barrial_distance=None,
    zonal_distance=None,
    suffix_tag=None,
    display_name_suffix=None,
):
    distance_by_category = dict(config.distance_by_category)
    if barrial_distance is not None:
        distance_by_category["BARRIAL"] = int(barrial_distance)
    if zonal_distance is not None:
        distance_by_category["ZONAL"] = int(zonal_distance)

    output_suffix = config.output_suffix
    if suffix_tag:
        output_suffix = f"{config.output_suffix}_{suffix_tag}"

    display_name = config.display_name
    if display_name_suffix:
        display_name = f"{config.display_name} {display_name_suffix}".strip()

    return replace(
        config,
        output_suffix=output_suffix,
        display_name=display_name,
        distance_by_category=distance_by_category,
    )


def run_named_config(key, **variant_kwargs):
    config = get_categorized_isochrone_config(key)
    if variant_kwargs:
        config = build_variant_config(config, **variant_kwargs)
    run_config(config)


def run_all_configs(**variant_kwargs):
    for config in iter_categorized_isochrone_configs():
        print(f"Procesando capa categorizada: {config.key}")
        if variant_kwargs:
            config = build_variant_config(config, **variant_kwargs)
        run_config(config)


def run_download_exports():
    export_script = BASE_DIR / "build-riobamba-isochrone-shapefile.py"
    sys.stdout.flush()
    subprocess.run([sys.executable, str(export_script)], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera isocronas categorizadas reutilizables para Riobamba.")
    parser.add_argument("dataset", nargs="?", help="Clave de la capa categorizada, por ejemplo: educacion o salud")
    parser.add_argument("--list", action="store_true", help="Muestra las capas categorizadas disponibles")
    parser.add_argument("--all", action="store_true", help="Procesa todas las capas categorizadas registradas")
    parser.add_argument("--exports", action="store_true", help="Actualiza tambien los ZIP de descarga al terminar")
    parser.add_argument("--distance-barrial", type=int, help="Sobrescribe la distancia de BARRIAL en metros")
    parser.add_argument("--distance-zonal", type=int, help="Sobrescribe la distancia de ZONAL en metros")
    parser.add_argument("--suffix-tag", help="Sufijo adicional para no sobreescribir salidas existentes")
    parser.add_argument("--display-name-suffix", help="Texto adicional para identificar la variante generada")
    args = parser.parse_args(argv)

    variant_kwargs = {
        "barrial_distance": args.distance_barrial,
        "zonal_distance": args.distance_zonal,
        "suffix_tag": args.suffix_tag,
        "display_name_suffix": args.display_name_suffix,
    }
    has_variant = any(value not in (None, "") for value in variant_kwargs.values())

    if args.exports and has_variant:
        parser.error("--exports no es compatible con variantes temporales. Genera la variante primero y registra una exportacion dedicada si la necesitas.")

    if args.list:
        for config in iter_categorized_isochrone_configs():
            key = config.key
            print(f"{key}: {config.display_name} -> {config.resolve_source_zip()}")
        return

    if args.all and args.dataset:
        parser.error("Usa una capa puntual o --all, pero no ambos a la vez.")

    if args.all:
        run_all_configs(**variant_kwargs)
        if args.exports:
            run_download_exports()
        return

    if not args.dataset:
        available = ", ".join(sorted(CATEGORIZED_ISOCHRONE_CONFIGS))
        parser.error(f"Debes indicar una capa. Disponibles: {available}")

    run_named_config(args.dataset, **variant_kwargs)
    if args.exports:
        run_download_exports()


if __name__ == "__main__":
    main()
