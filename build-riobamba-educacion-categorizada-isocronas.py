import collections
import heapq
import json
import math
import shutil
import zipfile
from pathlib import Path

import networkx as nx
import shapefile
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
ZIP_PATH = Path(r"E:\Riobamba\equipamientos\EDUCACION 2\EDUCACION_CATEGORIZADO.zip")
OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"

OUTPUT_EQUIPAMIENTOS = DATA_DIR / "riobamba_educacion_categorizada.geojson"
OUTPUT_EQUIPAMIENTOS_STATS = DATA_DIR / "riobamba_educacion_categorizada_stats.json"
OUTPUT_ISOCRONAS = DATA_DIR / "riobamba_isocronas_educacion_categorizada.geojson"
OUTPUT_ISOCRONAS_STATS = DATA_DIR / "riobamba_isocronas_educacion_categorizada_stats.json"
EXTRACT_DIR = DATA_DIR / "_tmp_educacion_categorizada"

DISTANCE_BY_CATEGORY = {
    "BARRIAL": 400,
    "ZONAL": 1000,
}
MANZANA_OVERLAP_RATIO_THRESHOLD = 0.25
MANZANA_REP_BUFFER_METERS = 20
EXTERNAL_CLOSE_GAP_METERS = 10
MIN_COMPONENT_AREA_M2 = 1200
MIN_COMPONENT_RATIO = 0.04
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


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
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
    return polygon.buffer(0)


def max_distance_to_geometry_boundary(geometry, source_point):
    max_distance = 0.0
    for part in polygon_parts(geometry):
        for x, y in part.exterior.coords:
            distance = source_point.distance(Point(x, y))
            if distance > max_distance:
                max_distance = distance
    return max_distance


def align_polygon_to_manzanas(manzana_features, isochrone_polygon, source_point, target_distance_m):
    selected_geometries = []
    selected_ids = []
    selection_buffer = isochrone_polygon.buffer(MANZANA_REP_BUFFER_METERS)
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
        if max_distance_to_geometry_boundary(manzana_geom, source_point) > max_vertex_distance:
            continue

        selected_geometries.append(manzana_geom)
        if manzana_id:
            selected_ids.append(manzana_id)

    if not selected_geometries:
        return isochrone_polygon, []

    return unary_union(selected_geometries), selected_ids


def polygon_parts(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if not part.is_empty]
    return []


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
    filtered = keep_significant_components(
        holeless,
        MIN_COMPONENT_AREA_M2,
        MIN_COMPONENT_RATIO,
    )
    cleaned = filtered.buffer(0)
    if cleaned.is_empty:
        return holeless
    return cleaned


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


def extract_source_records():
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {ZIP_PATH}")

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(EXTRACT_DIR)

    shp_path = next(EXTRACT_DIR.rglob("*.shp"), None)
    if shp_path is None:
        raise FileNotFoundError("No se encontro un shapefile dentro del ZIP de educacion.")

    reader = shapefile.Reader(str(shp_path))
    try:
        records = []
        features = []
        category_counter = collections.Counter()

        for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = shape_record.record.as_dict()
            geometry_utm = shape(shape_record.shape.__geo_interface__)
            categoria = normalize_text(record.get("CATEGORIA")).upper()
            nombre = normalize_text(record.get("Nombre_Equ"))
            equipamien = normalize_text(record.get("Equipamien"))
            codigo = normalize_text(record.get("codigo"))
            distance_m = DISTANCE_BY_CATEGORY.get(categoria)

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
        shutil.rmtree(EXTRACT_DIR, ignore_errors=True)

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_zip": str(ZIP_PATH),
        "summary": {
            "total_equipamientos": len(records),
            "con_isocrona": sum(1 for item in records if item["properties"]["genera_isocrona"]),
            "sin_isocrona": sum(1 for item in records if not item["properties"]["genera_isocrona"]),
            "categorias": len(category_counter),
        },
        "by_categoria": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
    }

    return records, {"type": "FeatureCollection", "features": features}, stats


def build_single_isochrone(record, manzana_features, base_graph, edge_tree, edge_geometries, edge_metadata):
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
    aligned_polygon, covered_manzanas = align_polygon_to_manzanas(
        manzana_features,
        exact_polygon,
        source_point,
        distance_m,
    )
    final_polygon = homogenize_aligned_polygon(aligned_polygon)
    if final_polygon.is_empty:
        final_polygon = remove_internal_holes(aligned_polygon.buffer(0))
    if final_polygon.is_empty:
        final_polygon = exact_polygon

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
            "area_poligono_red_m2": round(exact_polygon.area, 2),
            "area_poligono_manzanas_m2": round(aligned_polygon.area, 2),
            "area_poligono_m2": round(final_polygon.area, 2),
            "representation": "manzana_aligned_external_boundary",
        },
    )


def ensure_cache_covers_sources(records, osm_payload):
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
                "La red OSM cacheada no cubre todos los equipamientos de educacion. "
                "Se necesita regenerar una cache mas amplia."
            )


def main():
    records, equipamientos_geojson, equipamientos_stats = extract_source_records()
    save_json(OUTPUT_EQUIPAMIENTOS, equipamientos_geojson)
    save_json(OUTPUT_EQUIPAMIENTOS_STATS, equipamientos_stats)

    manzanas_data = load_json(MANZANAS_PATH)
    osm_payload = load_json(OSM_CACHE_PATH)
    ensure_cache_covers_sources(records, osm_payload)
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
            record,
            manzanas_data["features"],
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
    output_stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_zip": str(ZIP_PATH),
        "source_osm_cache": str(OSM_CACHE_PATH),
        "summary": {
            "total_equipamientos": len(records),
            "total_isocronas": len(isocronas),
            "categorias_con_isocrona": len(generated_counter),
            "omitidos": sum(skipped_counter.values()),
            "manzanas_ajustadas": sum(int(feature["properties"].get("manzanas_ajustadas", 0) or 0) for feature in isocronas),
        },
        "by_categoria_source": equipamientos_stats["by_categoria"],
        "by_categoria_isocronas": dict(sorted(generated_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_categoria_omitidos": dict(sorted(skipped_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_distance_m": {
            "400": sum(1 for feature in isocronas if int(feature["properties"].get("distance_m", 0)) == 400),
            "1000": sum(1 for feature in isocronas if int(feature["properties"].get("distance_m", 0)) == 1000),
        },
        "observacion": (
            "Se generan isocronas solo para BARRIAL (400 m) y ZONAL (1000 m). "
            "Los registros CANTONAL no se procesan. El resultado final queda ajustado a manzanas "
            "censales, sin huecos internos y preparado para mostrar solo el limite exterior."
        ),
    }

    save_json(OUTPUT_ISOCRONAS, output_geojson)
    save_json(OUTPUT_ISOCRONAS_STATS, output_stats)

    print("Listo.")
    print(f"Equipamientos: {OUTPUT_EQUIPAMIENTOS}")
    print(f"Stats equip:   {OUTPUT_EQUIPAMIENTOS_STATS}")
    print(f"Isocronas:     {OUTPUT_ISOCRONAS}")
    print(f"Stats iso:     {OUTPUT_ISOCRONAS_STATS}")
    print(f"Total isocronas generadas: {len(isocronas)}")


if __name__ == "__main__":
    main()
