import collections
import json
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from riobamba_categorized_isocronas import (
    DATA_DIR,
    MANZANAS_PATH,
    MANZANAS_STATS_PATH,
    build_edge_index,
    build_graph,
    build_single_isochrone,
    build_source_feature,
    load_json,
    save_json,
    to_utm,
    transformer_to_utm,
    transformer_to_wgs,
)


SOURCE_PUBLIC_PATH = DATA_DIR / "riobamba_entorno_publico.geojson"
OSM_CACHE_PATH = DATA_DIR / "riobamba_osm_walk_network_5categorias_todas_plataformas.json"
BUFFER_METERS = 1800
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
RIOBAMBA_LON_RANGE = (-78.9, -78.45)
RIOBAMBA_LAT_RANGE = (-1.9, -1.45)


@dataclass(frozen=True)
class CategoryRun:
    key: str
    display_name: str
    tipo_eleme: str
    output_suffix: str

    @property
    def output_equipamientos(self) -> Path:
        return DATA_DIR / f"riobamba_{self.output_suffix}.geojson"

    @property
    def output_equipamientos_stats(self) -> Path:
        return DATA_DIR / f"riobamba_{self.output_suffix}_stats.json"

    @property
    def output_isocronas(self) -> Path:
        return DATA_DIR / f"riobamba_isocronas_{self.output_suffix}.geojson"

    @property
    def output_isocronas_stats(self) -> Path:
        return DATA_DIR / f"riobamba_isocronas_{self.output_suffix}_stats.json"


CATEGORY_RUNS = [
    CategoryRun("educacion", "educacion todas las plataformas", "Educación", "educacion_categorizada_todas_plataformas_1000m"),
    CategoryRun("recreacion", "recreacion y deporte todas las plataformas", "Recreativo y Deporte", "recreacion_deporte_categorizada_todas_plataformas_1000m"),
    CategoryRun("bienestar", "bienestar social todas las plataformas", "Bienestar Social", "bienestar_social_categorizada_todas_plataformas_1000m"),
    CategoryRun("cultura", "cultura todas las plataformas", "Cultural", "cultura_categorizada_todas_plataformas_1000m"),
    CategoryRun("salud", "salud todas las plataformas", "Salud", "salud_categorizada_todas_plataformas_1000m"),
]


def normalize_text(value):
    return str(value or "").strip()


def normalized_key(value):
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def category_matches(value, expected):
    return normalized_key(value) == normalized_key(expected)


def get_distance_by_tipologia(tipologia):
    normalized = normalized_key(tipologia).upper()
    if normalized == "BARRIAL":
        return 1000
    if normalized == "ZONAL":
        return 1000
    return 0


def is_valid_riobamba_coordinate(coordinates):
    if not coordinates or len(coordinates) != 2:
        return False
    lon, lat = coordinates
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return False
    if lon == 0 and lat == 0:
        return False
    return (
        RIOBAMBA_LON_RANGE[0] <= float(lon) <= RIOBAMBA_LON_RANGE[1]
        and RIOBAMBA_LAT_RANGE[0] <= float(lat) <= RIOBAMBA_LAT_RANGE[1]
    )


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


def post_overpass(query):
    last_error = None
    for index, url in enumerate(OVERPASS_URLS):
        try:
            response = requests.post(
                url,
                data=query,
                timeout=180,
                headers={
                    "Content-Type": "text/plain",
                    "User-Agent": "codex-riobamba-5categorias/1.0",
                },
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            last_error = error
            if index < len(OVERPASS_URLS) - 1:
                time.sleep(1.5 + index)
                continue
            raise last_error


def fetch_osm_tile(bounds, depth=0, max_depth=4):
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
            time.sleep(1.5 + depth)
            merged = {}
            for sub_bounds in subdivide_bounds(bounds):
                for element in fetch_osm_tile(sub_bounds, depth + 1, max_depth):
                    merged[element["id"]] = element
            return list(merged.values())
        raise


def fetch_osm_ways(bounds, use_cache=True):
    if use_cache and OSM_CACHE_PATH.exists():
        return load_json(OSM_CACHE_PATH)

    merged = {}
    for tile in subdivide_bounds(bounds):
        for element in fetch_osm_tile(tile, depth=0, max_depth=2):
            merged[element["id"]] = element

    payload = {"elements": list(merged.values())}
    save_json(OSM_CACHE_PATH, payload)
    return payload


def build_bounds_for_records(records):
    buffered = unary_union([item["geometry_utm"] for item in records]).buffer(BUFFER_METERS)
    west, south, east, north = transform(transformer_to_wgs.transform, buffered).bounds
    return (west, south, east, north)


def extract_records_for_category(run):
    payload = load_json(SOURCE_PUBLIC_PATH)
    records = []
    features = []
    category_counter = collections.Counter()
    by_platform = collections.Counter()
    invalid_counter = 0

    for index, feature in enumerate(payload.get("features", []), start=1):
        props = feature.get("properties", {})
        if not category_matches(props.get("tipo_eleme"), run.tipo_eleme):
            continue

        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if not is_valid_riobamba_coordinate(coordinates):
            invalid_counter += 1
            continue

        geometry_utm = to_utm(shape(feature["geometry"]))
        tipologia = normalize_text(props.get("tipologia")).upper()
        distance_m = get_distance_by_tipologia(tipologia)
        nombre = (
            normalize_text(props.get("nombre_equ"))
            or normalize_text(props.get("nombre_ins"))
            or normalize_text(props.get("elemento"))
            or f"{run.key}_{index:03d}"
        )
        platform_name = normalize_text(props.get("platform_name") or props.get("plataforma")) or None

        category_counter[tipologia or "SIN_CATEGORIA"] += 1
        by_platform[platform_name or "SIN_PLATAFORMA"] += 1

        out_props = {
            "source_id": len(records) + 1,
            "objectid": len(records) + 1,
            "codigo": normalize_text(props.get("codigo")) or f"{run.key[:3].upper()}_{index:04d}",
            "equipamien": run.tipo_eleme,
            "nombre": nombre,
            "categoria": tipologia,
            "isocrona_distance_m": distance_m,
            "genera_isocrona": bool(distance_m),
            "platform_name": platform_name,
            "plataforma": platform_name,
            "elemento": normalize_text(props.get("elemento")),
            "parroquia": normalize_text(props.get("parroquia")),
            "tipo_equip": normalize_text(props.get("tipo_equip")),
            "tipologia": normalize_text(props.get("tipologia")),
            "shape_area": 0.0,
            "shape_leng": 0.0,
        }

        records.append({"properties": out_props, "geometry_utm": geometry_utm})
        features.append(build_source_feature(geometry_utm, out_props))

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_geojson": str(SOURCE_PUBLIC_PATH),
        "summary": {
            "total_equipamientos": len(records),
            "con_isocrona": sum(1 for item in records if item["properties"]["genera_isocrona"]),
            "sin_isocrona": sum(1 for item in records if not item["properties"]["genera_isocrona"]),
            "categorias": len(category_counter),
            "plataformas_con_puntos": len([key for key in by_platform if key != "SIN_PLATAFORMA"]),
            "registros_fuera_rango": invalid_counter,
        },
        "by_categoria": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_plataforma": dict(sorted(by_platform.items(), key=lambda item: (-item[1], item[0]))),
    }
    return records, {"type": "FeatureCollection", "features": features}, stats


def run_category(run, manzanas_features, manzana_stats_by_id, base_graph, edge_tree, edge_geometries, edge_metadata):
    records, equipamientos_geojson, equipamientos_stats = extract_records_for_category(run)
    save_json(run.output_equipamientos, equipamientos_geojson)
    save_json(run.output_equipamientos_stats, equipamientos_stats)

    isocronas = []
    generated_counter = collections.Counter()
    skipped_counter = collections.Counter()

    for record in records:
        categoria = record["properties"]["categoria"] or "SIN_CATEGORIA"
        if not record["properties"]["genera_isocrona"]:
            skipped_counter[categoria] += 1
            continue

        feature = build_single_isochrone(
            None,
            record,
            manzanas_features,
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

    distance_breakdown = collections.Counter(
        int(feature["properties"].get("distance_m", 0) or 0)
        for feature in isocronas
        if int(feature["properties"].get("distance_m", 0) or 0) > 0
    )

    output_geojson = {"type": "FeatureCollection", "features": isocronas}
    output_stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_geojson": str(SOURCE_PUBLIC_PATH),
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
            f"Isocronas de {run.display_name} usando el levantamiento publico de todas las plataformas. "
            "BARRIAL y ZONAL se generan a 1000 m. CANTONAL no se procesa. "
            "Las manzanas grandes se recortan al limite exacto de red para evitar extensiones mayores "
            "a la distancia objetivo y el resultado final se prepara para mostrar solo el limite exterior."
        ),
    }

    save_json(run.output_isocronas, output_geojson)
    save_json(run.output_isocronas_stats, output_stats)

    print("Listo.")
    print(f"Equipamientos {run.display_name}: {run.output_equipamientos}")
    print(f"Stats {run.display_name}:         {run.output_equipamientos_stats}")
    print(f"Isocronas {run.display_name}:     {run.output_isocronas}")
    print(f"Stats iso {run.display_name}:     {run.output_isocronas_stats}")
    print(f"Total isocronas generadas: {len(isocronas)}")


def main():
    all_records = []
    prepared = []
    for run in CATEGORY_RUNS:
        records, _, _ = extract_records_for_category(run)
        prepared.append((run, records))
        all_records.extend([record for record in records if record["properties"]["genera_isocrona"]])

    if not all_records:
        raise RuntimeError("No se encontraron equipamientos BARRIAL/ZONAL en las 5 categorias del entorno publico.")

    bounds = build_bounds_for_records(all_records)
    osm_payload = fetch_osm_ways(bounds, use_cache=True)
    base_graph = build_graph(osm_payload)
    edge_tree, edge_geometries, edge_metadata = build_edge_index(base_graph)

    manzanas_data = load_json(MANZANAS_PATH)
    manzanas_stats = load_json(MANZANAS_STATS_PATH)
    manzana_stats_by_id = manzanas_stats.get("byMan", {})

    for run, _ in prepared:
        print(f"Procesando categoria ciudad completa: {run.key}")
        run_category(
            run,
            manzanas_data["features"],
            manzana_stats_by_id,
            base_graph,
            edge_tree,
            edge_geometries,
            edge_metadata,
        )


if __name__ == "__main__":
    main()
