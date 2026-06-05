import argparse
import collections
import shutil
import subprocess
import sys
from pathlib import Path

import shapefile
from shapely.geometry import Point, shape
from shapely.ops import transform as geom_transform

from riobamba_categorized_isocronas import (
    BASE_DIR,
    DATA_DIR,
    MANZANAS_PATH,
    MANZANAS_STATS_PATH,
    OSM_CACHE_PATH,
    align_polygon_to_manzanas,
    build_edge_index,
    build_graph,
    build_isochrone_polygon,
    build_polygon_feature,
    build_reachable_segments,
    build_source_feature,
    ensure_cache_covers_sources,
    extract_archive,
    homogenize_aligned_polygon,
    load_json,
    multi_source_reachable,
    nearest_edge_projection,
    normalize_text,
    population_total_for_manzanas,
    remove_internal_holes,
    save_json,
    split_edges_with_projected_sources,
    transformer_to_wgs,
)


SOURCE_ARCHIVE_CANDIDATES = (
    BASE_DIR / "paradas de bus.rar",
    Path(r"E:\Riobamba\equipamientos\Trasnporte\paradas de bus.rar"),
)

EXTRACT_DIR = DATA_DIR / "_tmp_paradas_bus"
OUTPUT_STOPS = DATA_DIR / "riobamba_paradas_bus.geojson"
OUTPUT_STOPS_STATS = DATA_DIR / "riobamba_paradas_bus_stats.json"
OUTPUT_ISOCHRONES = DATA_DIR / "riobamba_isocronas_paradas_bus.geojson"
OUTPUT_ISOCHRONES_STATS = DATA_DIR / "riobamba_isocronas_paradas_bus_stats.json"

DISTANCE_M = 400
DEFAULT_TYPE = "Parada de bus"
DEFAULT_CATEGORY = "PARADA_400M"


def flatten_geometry(geometry):
    return geom_transform(lambda x, y, z=None: (x, y), geometry)


def resolve_source_archive():
    for path in SOURCE_ARCHIVE_CANDIDATES:
        if path.exists():
            return path
    checked = ", ".join(str(path) for path in SOURCE_ARCHIVE_CANDIDATES)
    raise FileNotFoundError(f"No se encontro el archivo fuente de paradas de bus. Revise: {checked}")


def build_stop_name(lineas, index):
    if lineas:
        return f"Parada {index:03d} - Lineas {lineas}"
    return f"Parada de bus {index:03d}"


def extract_bus_stop_records():
    source_archive = resolve_source_archive()

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    extract_archive(source_archive, EXTRACT_DIR)
    shp_path = next(EXTRACT_DIR.rglob("*.shp"), None)
    if shp_path is None:
        raise FileNotFoundError("No se encontro un shapefile dentro del archivo de paradas de bus.")

    reader = shapefile.Reader(str(shp_path))
    try:
        records = []
        features = []
        route_counter = collections.Counter()

        for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = shape_record.record.as_dict()
            geometry_utm = flatten_geometry(shape(shape_record.shape.__geo_interface__))
            lineas = normalize_text(record.get("Name"))
            folder_path = normalize_text(record.get("FolderPath"))
            nombre = build_stop_name(lineas, index)
            codigo = f"PARADA_BUS_{index:03d}"

            properties = {
                "source_id": index,
                "objectid": int(record.get("OBJECTID", index) or index),
                "codigo": codigo,
                "equipamien": DEFAULT_TYPE,
                "nombre": nombre,
                "categoria": DEFAULT_CATEGORY,
                "isocrona_distance_m": DISTANCE_M,
                "genera_isocrona": True,
                "lineas": lineas,
                "folder_path": folder_path,
            }

            route_counter[lineas or "SIN_NOMBRE"] += 1
            records.append({"properties": properties, "geometry_utm": geometry_utm})
            features.append(build_source_feature(geometry_utm, properties))
    finally:
        reader.close()
        shutil.rmtree(EXTRACT_DIR, ignore_errors=True)

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_archive": str(source_archive),
        "summary": {
            "total_paradas": len(records),
            "distancia_isocrona_m": DISTANCE_M,
            "rutas_distintas": len(route_counter),
        },
        "by_lineas": dict(sorted(route_counter.items(), key=lambda item: (-item[1], item[0]))),
    }

    return records, {"type": "FeatureCollection", "features": features}, stats


def build_bus_stop_isochrone(record, manzana_features, manzana_stats_by_id, base_graph, edge_tree, edge_geometries, edge_metadata):
    props = record["properties"]
    geometry_utm = record["geometry_utm"]
    distance_m = int(props["isocrona_distance_m"])
    source_point_geom = geometry_utm.representative_point()

    projection = nearest_edge_projection(
        (source_point_geom.x, source_point_geom.y),
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
    stop_lon, stop_lat = transformer_to_wgs.transform(source_point_geom.x, source_point_geom.y)

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
        reachable_segments=segments,
    )
    final_polygon = homogenize_aligned_polygon(aligned_polygon)
    if final_polygon.is_empty:
        final_polygon = remove_internal_holes(aligned_polygon.buffer(0))
    if final_polygon.is_empty:
        final_polygon = exact_polygon

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
            "lineas": props["lineas"],
            "distance_m": distance_m,
            "mode": "walking",
            "origin_type": "parada_bus",
            "source_type": "parada_bus_manzana_aligned_external",
            "snap_m": round(float(projection["snap_m"]), 2),
            "source_node_id": str(source_entry.get("node_id")),
            "source_lon": round(source_lon, 8),
            "source_lat": round(source_lat, 8),
            "parada_lon": round(stop_lon, 8),
            "parada_lat": round(stop_lat, 8),
            "nodos_alcanzables": len(reachable),
            "segmentos_red": len(segments),
            "longitud_red_m": round(total_length, 2),
            "manzanas_ajustadas": len(covered_manzanas),
            "population_total": population_total,
            "area_poligono_red_m2": round(exact_polygon.area, 2),
            "area_poligono_manzanas_m2": round(aligned_polygon.area, 2),
            "area_poligono_m2": round(final_polygon.area, 2),
            "representation": "manzana_aligned_external_boundary",
        },
    )


def run_exports():
    export_script = BASE_DIR / "build-riobamba-isochrone-shapefile.py"
    sys.stdout.flush()
    subprocess.run([sys.executable, str(export_script)], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera isocronas de 400 m para paradas de bus de Riobamba.")
    parser.add_argument("--exports", action="store_true", help="Actualiza tambien los ZIP de descarga al terminar")
    args = parser.parse_args(argv)

    records, stops_geojson, stops_stats = extract_bus_stop_records()
    save_json(OUTPUT_STOPS, stops_geojson)
    save_json(OUTPUT_STOPS_STATS, stops_stats)

    manzanas_data = load_json(MANZANAS_PATH)
    manzanas_stats = load_json(MANZANAS_STATS_PATH)
    manzana_stats_by_id = manzanas_stats.get("byMan", {})
    osm_payload = load_json(OSM_CACHE_PATH)
    ensure_cache_covers_sources(records, osm_payload, "paradas de bus")
    base_graph = build_graph(osm_payload)
    edge_tree, edge_geometries, edge_metadata = build_edge_index(base_graph)

    isochrones = []
    generated_counter = collections.Counter()
    skipped_counter = collections.Counter()

    for record in records:
        feature = build_bus_stop_isochrone(
            record,
            manzanas_data["features"],
            manzana_stats_by_id,
            base_graph,
            edge_tree,
            edge_geometries,
            edge_metadata,
        )
        if feature is None:
            skipped_counter["SIN_RED"] += 1
            continue

        isochrones.append(feature)
        generated_counter["400"] += 1

    isochrones.sort(key=lambda feature: (feature["properties"].get("nombre", ""), feature["properties"].get("codigo", "")))

    output_geojson = {"type": "FeatureCollection", "features": isochrones}
    output_stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_archive": str(resolve_source_archive()),
        "source_osm_cache": str(OSM_CACHE_PATH),
        "summary": {
            "total_paradas": len(records),
            "total_isocronas": len(isochrones),
            "omitidos": sum(skipped_counter.values()),
            "distancia_m": DISTANCE_M,
            "manzanas_ajustadas": sum(int(feature["properties"].get("manzanas_ajustadas", 0) or 0) for feature in isochrones),
        },
        "by_distance_m": {"400": len(isochrones)},
        "by_resultado": {
            "generadas": len(isochrones),
            "sin_red": skipped_counter.get("SIN_RED", 0),
        },
        "observacion": (
            "Se generan isocronas de 400 m para cada parada de bus. "
            "El resultado final queda ajustado a manzanas censales, sin huecos internos "
            "y preparado para mostrar solo el limite exterior."
        ),
    }

    save_json(OUTPUT_ISOCHRONES, output_geojson)
    save_json(OUTPUT_ISOCHRONES_STATS, output_stats)

    print("Listo.")
    print(f"Paradas de bus:      {OUTPUT_STOPS}")
    print(f"Stats paradas:       {OUTPUT_STOPS_STATS}")
    print(f"Isocronas paradas:   {OUTPUT_ISOCHRONES}")
    print(f"Stats isocronas:     {OUTPUT_ISOCHRONES_STATS}")
    print(f"Total isocronas: {len(isochrones)}")

    if args.exports:
        run_exports()


if __name__ == "__main__":
    main()
