import collections
import json
import math
import re
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
DUPLICATE_THRESHOLD_METERS = 15
DUPLICATE_GENERIC_NAMES = {
    "sin nombre",
    "prueba",
    "completo",
    "area verde",
    "area verde sin mantenimiento",
    "parque del sector",
    "call3 c3 y araguacos",
}
DUPLICATE_NAME_STOPWORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "tras",
    "para",
    "por",
    "en",
    "un",
    "una",
}
DUPLICATE_LEADING_ALIAS_TOKENS = {
    "iglesia",
    "parque",
    "unidad",
    "ue",
    "escuela",
    "colegio",
    "centro",
    "subcentro",
    "casa",
    "parroquia",
}


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


def get_feature_name(properties, fallback=""):
    return (
        normalize_text(properties.get("nombre_equ"))
        or normalize_text(properties.get("nombre_ins"))
        or normalize_text(properties.get("elemento"))
        or normalize_text(fallback)
    )


def get_duplicate_name_tokens(value):
    return [
        token
        for token in re.split(r"[^a-z0-9]+", normalized_key(value))
        if token and token not in DUPLICATE_NAME_STOPWORDS
    ]


def get_duplicate_leading_token(value):
    tokens = get_duplicate_name_tokens(value)
    return tokens[0] if tokens else ""


def get_duplicate_token_overlap(left_value, right_value):
    left_tokens = set(get_duplicate_name_tokens(left_value))
    right_tokens = set(get_duplicate_name_tokens(right_value))
    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))


def is_generic_duplicate_name(value):
    return normalized_key(value) in DUPLICATE_GENERIC_NAMES


def are_probable_duplicate_names(left_value, right_value):
    left_name = normalized_key(left_value)
    right_name = normalized_key(right_value)
    if not left_name or not right_name:
        return False

    if left_name == right_name:
        return True

    if is_generic_duplicate_name(left_name) or is_generic_duplicate_name(right_name):
        return True

    if left_name in right_name or right_name in left_name:
        return True

    if get_duplicate_token_overlap(left_name, right_name) >= 0.55:
        return True

    left_lead = get_duplicate_leading_token(left_name)
    right_lead = get_duplicate_leading_token(right_name)
    return bool(left_lead and left_lead == right_lead and left_lead in DUPLICATE_LEADING_ALIAS_TOKENS)


def point_distance_meters(left_coords, right_coords):
    left_lon, left_lat = left_coords
    right_lon, right_lat = right_coords
    mean_lat_rad = ((left_lat + right_lat) / 2.0) * math.pi / 180.0
    dx = (right_lon - left_lon) * 111320.0 * math.cos(mean_lat_rad)
    dy = (right_lat - left_lat) * 110540.0
    return math.sqrt(dx * dx + dy * dy)


def get_feature_estado_rank(properties):
    estado = normalized_key(properties.get("estado") or properties.get("ESTADO") or "")
    if "excelente" in estado or "muy bueno" in estado:
        return 4
    if "bueno" in estado:
        return 3
    if "regular" in estado:
        return 2
    if "malo" in estado:
        return 1
    return 0


def get_feature_completeness_score(properties):
    score = 0
    for value in properties.values():
        if value is None:
            continue
        if isinstance(value, str):
            score += 1 if value.strip() else 0
        else:
            score += 1
    return score


def get_duplicate_name_quality_score(value):
    normalized_name = normalized_key(value)
    if not normalized_name:
        return 0

    score = min(len(normalized_name), 48)
    score += len(get_duplicate_name_tokens(normalized_name)) * 12

    if is_generic_duplicate_name(normalized_name):
        score -= 80

    if re.search(r"\btras\b|\bfrente\b|\bcerca\b|\bjunto\b|\bsector\b", normalized_name):
        score -= 8

    return score


def get_duplicate_feature_score(properties, dedupe_name):
    return (
        get_feature_estado_rank(properties) * 1000
        + get_feature_completeness_score(properties)
        + get_duplicate_name_quality_score(dedupe_name)
    )


def get_duplicate_core_key(properties):
    parts = [
        normalized_key(properties.get("tipo_eleme")),
        normalized_key(properties.get("elemento")),
        normalized_key(properties.get("platform_name") or properties.get("plataforma")),
        normalized_key(properties.get("parroquia")),
        normalized_key(properties.get("tipologia")),
        normalized_key(properties.get("tipo_equip") or properties.get("gestion")),
    ]
    if sum(1 for part in parts if part) < 3:
        return ""
    return "||".join(parts)


def dedupe_prepared_records(records):
    kept_records = []
    duplicate_summary = {
        "duplicates_removed": 0,
        "duplicates_exact": 0,
        "duplicates_probable": 0,
    }

    for record in records:
        match_index = None
        match_type = ""

        for index, kept_record in enumerate(kept_records):
            if point_distance_meters(record["source_coords"], kept_record["source_coords"]) > DUPLICATE_THRESHOLD_METERS:
                continue

            exact_match = bool(
                record["dedupe_name_key"]
                and kept_record["dedupe_name_key"]
                and record["dedupe_name_key"] == kept_record["dedupe_name_key"]
            )
            probable_match = bool(
                record["dedupe_core_key"]
                and kept_record["dedupe_core_key"]
                and record["dedupe_core_key"] == kept_record["dedupe_core_key"]
                and are_probable_duplicate_names(record["dedupe_name"], kept_record["dedupe_name"])
            )

            if exact_match or probable_match:
                match_index = index
                match_type = "exact" if exact_match else "probable"
                break

        if match_index is None:
            kept_records.append(record)
            continue

        duplicate_summary["duplicates_removed"] += 1
        duplicate_summary[f"duplicates_{match_type}"] += 1

        current_score = get_duplicate_feature_score(record["raw_properties"], record["dedupe_name"])
        existing_score = get_duplicate_feature_score(
            kept_records[match_index]["raw_properties"],
            kept_records[match_index]["dedupe_name"],
        )
        if current_score > existing_score:
            kept_records[match_index] = record

    return kept_records, duplicate_summary


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
    raw_records = []
    invalid_counter = 0

    for feature in payload.get("features", []):
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
        record_index = len(raw_records) + 1
        source_id = int(props.get("source_id", 0) or 0) or record_index
        nombre = get_feature_name(props, fallback=f"{run.key}_{record_index:03d}")
        platform_name = normalize_text(props.get("platform_name") or props.get("plataforma")) or None

        out_props = {
            "source_id": source_id,
            "category_record_id": record_index,
            "public_source_id": source_id,
            "objectid": record_index,
            "codigo": normalize_text(props.get("codigo")) or f"{run.key[:3].upper()}_{record_index:04d}",
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

        raw_records.append(
            {
                "properties": out_props,
                "geometry_utm": geometry_utm,
                "source_coords": (float(coordinates[0]), float(coordinates[1])),
                "raw_properties": props,
                "dedupe_name": nombre,
                "dedupe_name_key": normalized_key(nombre),
                "dedupe_core_key": get_duplicate_core_key(props),
            }
        )

    records, duplicate_summary = dedupe_prepared_records(raw_records)
    features = [build_source_feature(item["geometry_utm"], item["properties"]) for item in records]
    category_counter = collections.Counter(
        (item["properties"].get("categoria") or "SIN_CATEGORIA")
        for item in records
    )
    category_counter_raw = collections.Counter(
        (item["properties"].get("categoria") or "SIN_CATEGORIA")
        for item in raw_records
    )
    by_platform = collections.Counter(
        (item["properties"].get("platform_name") or "SIN_PLATAFORMA")
        for item in records
    )

    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_geojson": str(SOURCE_PUBLIC_PATH),
        "summary": {
            "total_equipamientos_bruto": len(raw_records),
            "total_equipamientos": len(records),
            "con_isocrona": sum(1 for item in records if item["properties"]["genera_isocrona"]),
            "sin_isocrona": sum(1 for item in records if not item["properties"]["genera_isocrona"]),
            "categorias": len(category_counter),
            "plataformas_con_puntos": len([key for key in by_platform if key != "SIN_PLATAFORMA"]),
            "registros_fuera_rango": invalid_counter,
            "duplicates_removed": duplicate_summary["duplicates_removed"],
            "duplicates_exact": duplicate_summary["duplicates_exact"],
            "duplicates_probable": duplicate_summary["duplicates_probable"],
        },
        "by_categoria_bruto": dict(sorted(category_counter_raw.items(), key=lambda item: (-item[1], item[0]))),
        "by_categoria": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_plataforma": dict(sorted(by_platform.items(), key=lambda item: (-item[1], item[0]))),
        "observacion": (
            f"Se depuraron {duplicate_summary['duplicates_removed']} puntos duplicados "
            f"({duplicate_summary['duplicates_exact']} exactos y {duplicate_summary['duplicates_probable']} probables) "
            "antes de preparar los equipamientos de esta categoria."
        ),
    }
    return records, {"type": "FeatureCollection", "features": features}, stats


def build_isocronas_stats(run, equipamientos_stats, records, isocronas, skipped_counter, mode):
    generated_counter = collections.Counter(
        feature["properties"].get("categoria") or "SIN_CATEGORIA"
        for feature in isocronas
    )
    distance_breakdown = collections.Counter(
        int(feature["properties"].get("distance_m", 0) or 0)
        for feature in isocronas
        if int(feature["properties"].get("distance_m", 0) or 0) > 0
    )

    mode_note = (
        "Se reconstruyeron geometrías usando la red vial OSM en caché."
        if mode == "network_rebuilt"
        else "Se conservaron las geometrías existentes y se filtraron las asociadas a puntos duplicados."
    )

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_geojson": str(SOURCE_PUBLIC_PATH),
        "source_osm_cache": str(OSM_CACHE_PATH),
        "summary": {
            "total_equipamientos_bruto": int(equipamientos_stats["summary"].get("total_equipamientos_bruto", len(records))),
            "total_equipamientos": len(records),
            "total_isocronas": len(isocronas),
            "categorias_con_isocrona": len(generated_counter),
            "omitidos": sum(skipped_counter.values()),
            "manzanas_ajustadas": sum(int(feature["properties"].get("manzanas_ajustadas", 0) or 0) for feature in isocronas),
            "manzanas_grandes_recortadas": sum(
                int(feature["properties"].get("manzanas_grandes_recortadas", 0) or 0)
                for feature in isocronas
            ),
            "duplicates_removed": int(equipamientos_stats["summary"].get("duplicates_removed", 0) or 0),
            "duplicates_exact": int(equipamientos_stats["summary"].get("duplicates_exact", 0) or 0),
            "duplicates_probable": int(equipamientos_stats["summary"].get("duplicates_probable", 0) or 0),
        },
        "by_categoria_source": equipamientos_stats["by_categoria"],
        "by_categoria_source_bruto": equipamientos_stats.get("by_categoria_bruto", equipamientos_stats["by_categoria"]),
        "by_categoria_isocronas": dict(sorted(generated_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_categoria_omitidos": dict(sorted(skipped_counter.items(), key=lambda item: (-item[1], item[0]))),
        "by_distance_m": dict(sorted((str(distance), count) for distance, count in distance_breakdown.items())),
        "observacion": (
            f"Isocronas de {run.display_name} usando el levantamiento publico de todas las plataformas. "
            "BARRIAL y ZONAL se generan a 1000 m. CANTONAL no se procesa. "
            "Las manzanas grandes se recortan al limite exacto de red para evitar extensiones mayores "
            "a la distancia objetivo y el resultado final se prepara para mostrar solo el limite exterior. "
            f"{mode_note}"
        ),
    }


def filter_existing_isocronas(run, records):
    if not run.output_isocronas.exists():
        raise FileNotFoundError(
            f"No existe {run.output_isocronas.name} para reutilizar las isocronas actuales de {run.display_name}."
        )

    payload = load_json(run.output_isocronas)
    keep_source_ids = {
        int(item["properties"].get("source_id", 0) or 0)
        for item in records
        if item["properties"].get("genera_isocrona")
    }
    keep_codes = {
        normalize_text(item["properties"].get("codigo"))
        for item in records
        if item["properties"].get("genera_isocrona") and normalize_text(item["properties"].get("codigo"))
    }

    filtered = []
    matched_source_ids = set()
    matched_codes = set()
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        source_id = int(props.get("source_id", 0) or 0)
        code = normalize_text(props.get("codigo"))
        if source_id in keep_source_ids or (code and code in keep_codes):
            filtered.append(feature)
            if source_id:
                matched_source_ids.add(source_id)
            if code:
                matched_codes.add(code)

    filtered.sort(
        key=lambda feature: (
            feature["properties"].get("distance_m", 0),
            feature["properties"].get("categoria", ""),
            feature["properties"].get("nombre", ""),
        )
    )

    skipped_counter = collections.Counter()
    for record in records:
        categoria = record["properties"].get("categoria") or "SIN_CATEGORIA"
        if not record["properties"].get("genera_isocrona"):
            skipped_counter[categoria] += 1
            continue

        source_id = int(record["properties"].get("source_id", 0) or 0)
        code = normalize_text(record["properties"].get("codigo"))
        if source_id in matched_source_ids or (code and code in matched_codes):
            continue
        skipped_counter[f"{categoria}_SIN_EXISTENTE"] += 1

    return filtered, skipped_counter


def run_category(run, records, equipamientos_stats, manzanas_features, manzana_stats_by_id, base_graph, edge_tree, edge_geometries, edge_metadata):
    isocronas = []
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

    isocronas.sort(
        key=lambda feature: (
            feature["properties"].get("distance_m", 0),
            feature["properties"].get("categoria", ""),
            feature["properties"].get("nombre", ""),
        )
    )

    output_geojson = {"type": "FeatureCollection", "features": isocronas}
    output_stats = build_isocronas_stats(
        run,
        equipamientos_stats,
        records,
        isocronas,
        skipped_counter,
        "network_rebuilt",
    )

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
        records, equipamientos_geojson, equipamientos_stats = extract_records_for_category(run)
        save_json(run.output_equipamientos, equipamientos_geojson)
        save_json(run.output_equipamientos_stats, equipamientos_stats)
        prepared.append((run, records, equipamientos_stats))
        all_records.extend([record for record in records if record["properties"]["genera_isocrona"]])

    if not all_records:
        raise RuntimeError("No se encontraron equipamientos BARRIAL/ZONAL en las 5 categorias del entorno publico.")

    if OSM_CACHE_PATH.exists():
        bounds = build_bounds_for_records(all_records)
        osm_payload = fetch_osm_ways(bounds, use_cache=True)
        base_graph = build_graph(osm_payload)
        edge_tree, edge_geometries, edge_metadata = build_edge_index(base_graph)

        manzanas_data = load_json(MANZANAS_PATH)
        manzanas_stats = load_json(MANZANAS_STATS_PATH)
        manzana_stats_by_id = manzanas_stats.get("byMan", {})

        for run, records, equipamientos_stats in prepared:
            print(f"Procesando categoria ciudad completa: {run.key}")
            run_category(
                run,
                records,
                equipamientos_stats,
                manzanas_data["features"],
                manzana_stats_by_id,
                base_graph,
                edge_tree,
                edge_geometries,
                edge_metadata,
            )
        return

    print("No se encontro el cache OSM de ciudad completa. Se reutilizaran las isocronas existentes y se filtraran los puntos duplicados.")
    for run, records, equipamientos_stats in prepared:
        filtered_isocronas, skipped_counter = filter_existing_isocronas(run, records)
        save_json(run.output_isocronas, {"type": "FeatureCollection", "features": filtered_isocronas})
        save_json(
            run.output_isocronas_stats,
            build_isocronas_stats(
                run,
                equipamientos_stats,
                records,
                filtered_isocronas,
                skipped_counter,
                "filtered_existing",
            ),
        )
        print(f"Procesando categoria ciudad completa: {run.key}")
        print(f"Isocronas depuradas: {run.output_isocronas}")
        print(f"Stats iso depuradas: {run.output_isocronas_stats}")
        print(f"Total isocronas depuradas: {len(filtered_isocronas)}")


if __name__ == "__main__":
    main()
