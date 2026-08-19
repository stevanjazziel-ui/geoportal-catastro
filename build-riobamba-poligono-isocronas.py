import datetime as dt
import importlib.util
from pathlib import Path

from shapely.geometry import shape


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RIOBAMBA_DATA_DIR = BASE_DIR / "riobamba-censo-data"
POLYGON_PATH = DATA_DIR / "riobamba-poligono-referencia.geojson"

OUTPUT_ISOCHRONES = DATA_DIR / "riobamba-poligono-isocronas.geojson"
OUTPUT_NETWORK = DATA_DIR / "riobamba-poligono-red-vial-isocronas.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba-poligono-isocronas-stats.json"

DISTANCES_METERS = [200, 500]
SEARCH_BUFFER_METERS = 1400


def load_helper_module():
    helper_path = BASE_DIR / "build-riobamba-isocrona-n.py"
    spec = importlib.util.spec_from_file_location("riobamba_isocrona_boundary", helper_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def find_osm_cache():
    candidates = [
        RIOBAMBA_DATA_DIR / "riobamba_osm_walk_network_5categorias_todas_plataformas.json",
        RIOBAMBA_DATA_DIR / "riobamba_osm_walk_network_plataforma_n.json",
        BASE_DIR.parent / "riobamba-censo-data" / "riobamba_osm_walk_network_5categorias_todas_plataformas.json",
        BASE_DIR.parent / "riobamba-censo-data" / "riobamba_osm_walk_network_plataforma_n.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_reference_polygon(helper):
    payload = helper.load_geojson(POLYGON_PATH)
    polygon_feature = next(
        feature
        for feature in payload.get("features", [])
        if feature.get("properties", {}).get("feature_type") == "polygon"
    )
    return polygon_feature, shape(polygon_feature["geometry"])


def build_sources(helper, edge_tree, edge_geometries, edge_metadata, sampled_boundary_points):
    projected_sources = []
    for index, point_utm in enumerate(sampled_boundary_points, start=1):
        projection = helper.nearest_edge_projection(
            (point_utm.x, point_utm.y),
            edge_tree,
            edge_geometries,
            edge_metadata,
        )
        if projection is None:
            continue
        projected_sources.append(
            {
                "source_id": index,
                "sample_point_utm": point_utm,
                "initial_distance_m": float(projection["snap_m"]),
                **projection,
            }
        )
    return projected_sources


def summarize_snap(projected_sources):
    snap_values = sorted(source["snap_m"] for source in projected_sources)
    average_snap_m = round(sum(snap_values) / len(snap_values), 2) if snap_values else 0.0
    p95_snap_m = round(snap_values[max(0, len(snap_values) * 95 // 100 - 1)], 2) if snap_values else 0.0
    max_snap_m = round(snap_values[-1], 2) if snap_values else 0.0
    return average_snap_m, p95_snap_m, max_snap_m


def build_distance_outputs(helper, graph, projected_sources, manzana_features, manzana_stats_by_id, polygon_name, distance_m):
    reachable = helper.multi_source_reachable(graph, projected_sources, distance_m)
    segments, total_length = helper.build_reachable_segments(graph, reachable, distance_m)
    source_points = [source["projected_xy"] for source in projected_sources]
    base_polygon = helper.build_isochrone_polygon(segments, source_points)
    exact_polygon = base_polygon.buffer(0)
    if exact_polygon.is_empty:
        exact_polygon = base_polygon

    aligned_polygon, covered_manzanas = helper.align_polygon_to_manzanas(manzana_features, exact_polygon)
    population_total = helper.population_total_for_manzanas(covered_manzanas, manzana_stats_by_id)
    network_geom = helper.normalize_multilines(segments)

    return {
        "distance_m": distance_m,
        "reachable": reachable,
        "segments": segments,
        "network_geom": network_geom,
        "total_length": total_length,
        "exact_polygon": exact_polygon,
        "aligned_polygon": aligned_polygon,
        "covered_manzanas": covered_manzanas,
        "population_total": population_total,
        "polygon_name": polygon_name,
    }


def main():
    helper = load_helper_module()
    polygon_feature, polygon_geom = load_reference_polygon(helper)
    polygon_name = polygon_feature.get("properties", {}).get("name", "Poligono de referencia")

    manzanas_data = helper.load_geojson(helper.MANZANAS_PATH)
    manzanas_stats = helper.load_geojson(helper.MANZANAS_STATS_PATH)
    manzana_stats_by_id = manzanas_stats.get("byMan", {})

    polygon_geom_utm = helper.to_utm(polygon_geom)
    boundary_geom_utm = polygon_geom_utm.boundary
    sampled_boundary_points = helper.sample_boundary_points(boundary_geom_utm, helper.BOUNDARY_SAMPLE_STEP_METERS)

    cache_path = find_osm_cache()
    if cache_path:
        overpass_json = helper.load_geojson(cache_path)
        network_source = f"cache:{cache_path.name}"
    else:
        search_area = helper.to_wgs84(polygon_geom_utm.buffer(SEARCH_BUFFER_METERS))
        overpass_json = helper.fetch_osm_ways(search_area.bounds, use_cache=False)
        network_source = "overpass-api"

    base_graph = helper.build_graph(overpass_json)
    edge_tree, edge_geometries, edge_metadata = helper.build_edge_index(base_graph)
    projected_sources = build_sources(helper, edge_tree, edge_geometries, edge_metadata, sampled_boundary_points)
    graph = helper.split_edges_with_projected_sources(base_graph, projected_sources)

    source_node_count = len({source["node_id"] for source in projected_sources if source.get("node_id") is not None})
    average_snap_m, p95_snap_m, max_snap_m = summarize_snap(projected_sources)
    generated_at = dt.datetime.now().isoformat(timespec="seconds")

    isochrone_features = []
    network_features = []
    stats_by_distance = {}

    for distance_m in sorted(DISTANCES_METERS, reverse=True):
        result = build_distance_outputs(
            helper,
            graph,
            projected_sources,
            manzanas_data["features"],
            manzana_stats_by_id,
            polygon_name,
            distance_m,
        )

        isochrone_feature = helper.build_polygon_feature(
            result["exact_polygon"],
            {
                "nombre": f"Isocrona exacta de red {distance_m} m desde el borde de {polygon_name}",
                "target_name": polygon_name,
                "target_platform": polygon_name,
                "distance_m": distance_m,
                "mode": "walking",
                "source_type": "polygon_boundary",
                "boundary_samples": len(sampled_boundary_points),
                "source_nodes": source_node_count,
                "snap_promedio_m": average_snap_m,
                "snap_p95_m": p95_snap_m,
                "snap_max_m": max_snap_m,
                "nodos_alcanzables": len(result["reachable"]),
                "segmentos_red": len(result["segments"]),
                "longitud_red_m": round(result["total_length"], 2),
                "population_total": result["population_total"],
                "manzanas_ajustadas": len(result["covered_manzanas"]),
                "area_poligono_red_m2": round(result["exact_polygon"].area, 2),
                "area_poligono_manzanas_m2": round(result["aligned_polygon"].area, 2),
                "area_poligono_m2": round(result["exact_polygon"].area, 2),
            },
        )

        network_feature = helper.build_line_feature(
            result["network_geom"],
            {
                "nombre": f"Red vial OSM alcanzable a {distance_m} m desde el borde de {polygon_name}",
                "target_name": polygon_name,
                "target_platform": polygon_name,
                "distance_m": distance_m,
                "mode": "walking",
                "source_type": "polygon_boundary",
                "boundary_samples": len(sampled_boundary_points),
                "source_nodes": source_node_count,
                "snap_promedio_m": average_snap_m,
                "snap_p95_m": p95_snap_m,
                "snap_max_m": max_snap_m,
                "segmentos_red": len(result["segments"]),
                "longitud_red_m": round(result["total_length"], 2),
            },
        )

        stats_by_distance[str(distance_m)] = {
            "generated_at": generated_at,
            "target_name": polygon_name,
            "distance_m": distance_m,
            "mode": "walking",
            "source_type": "polygon_boundary",
            "boundary_samples": len(sampled_boundary_points),
            "source_nodes": source_node_count,
            "snap_promedio_m": average_snap_m,
            "snap_p95_m": p95_snap_m,
            "snap_max_m": max_snap_m,
            "nodos_alcanzables": len(result["reachable"]),
            "segmentos_red": len(result["segments"]),
            "longitud_red_m": round(result["total_length"], 2),
            "population_total": result["population_total"],
            "manzanas_ajustadas": len(result["covered_manzanas"]),
            "area_poligono_red_m2": round(result["exact_polygon"].area, 2),
            "area_poligono_manzanas_m2": round(result["aligned_polygon"].area, 2),
            "area_poligono_m2": round(result["exact_polygon"].area, 2),
            "network_source": network_source,
            "source": "OpenStreetMap peatonal + proyeccion del borde del poligono a la red + descuento del acceso hasta la via + referencia de cobertura contra manzanas censales",
        }

        isochrone_features.append(isochrone_feature)
        network_features.append(network_feature)

    helper.save_json(OUTPUT_ISOCHRONES, {"type": "FeatureCollection", "features": isochrone_features})
    helper.save_json(OUTPUT_NETWORK, {"type": "FeatureCollection", "features": network_features})
    helper.save_json(
        OUTPUT_STATS,
        {
            "generated_at": generated_at,
            "target_name": polygon_name,
            "source_type": "polygon_boundary",
            "boundary_samples": len(sampled_boundary_points),
            "source_nodes": source_node_count,
            "network_source": network_source,
            "distances": stats_by_distance,
        },
    )

    print("Listo.")
    print(f"Poligono origen: {polygon_name}")
    print(f"Muestras del borde: {len(sampled_boundary_points)}")
    print(f"Nodos origen sobre red: {source_node_count}")
    print(f"Snap promedio al eje vial: {average_snap_m} m")
    print(f"Snap p95 al eje vial: {p95_snap_m} m")
    print(f"Snap maximo al eje vial: {max_snap_m} m")
    for distance_m in DISTANCES_METERS:
        stats = stats_by_distance[str(distance_m)]
        print(
            f"{distance_m} m -> segmentos {stats['segmentos_red']}, "
            f"longitud {stats['longitud_red_m']} m, "
            f"area {stats['area_poligono_m2']} m2, "
            f"poblacion ref {stats['population_total']}"
        )


if __name__ == "__main__":
    main()
