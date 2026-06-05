import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiLineString, shape, mapping
from shapely.ops import linemerge, transform, unary_union


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
EXTRACT_DIR = DATA_DIR / "_tmp_transporte_intracantonal"

SOURCE_ZIP_CANDIDATES = (
    BASE_DIR / "TIntracantonalRbbaSep.zip",
    Path(r"E:\Riobamba\equipamientos\Trasnporte\TIntracantonalRbbaSep.zip"),
)

TARGET_CONTOUR_PATH = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_ajustada_manzanas.geojson"
OUTPUT_LINES_PATH = DATA_DIR / "riobamba_transporte_intracantonal_recortado_carto_400m.geojson"
OUTPUT_BUFFER_PATH = DATA_DIR / "riobamba_transporte_intracantonal_buffer_carto_200m.geojson"
OUTPUT_STATS_PATH = DATA_DIR / "riobamba_transporte_intracantonal_400m_stats.json"

TARGET_CRS = CRS.from_epsg(32717)
WGS84 = CRS.from_epsg(4326)
BUFFER_SIDE_METERS = 200
BUFFER_TOTAL_METERS = BUFFER_SIDE_METERS * 2


def resolve_source_zip():
    for path in SOURCE_ZIP_CANDIDATES:
        if path.exists():
            return path
    checked = ", ".join(str(path) for path in SOURCE_ZIP_CANDIDATES)
    raise FileNotFoundError(f"No se encontro el ZIP de transporte. Revise: {checked}")


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def force_2d(geometry):
    return transform(lambda x, y, z=None: (x, y), geometry)


def normalize_text(value):
    text = str(value or "").strip()
    if any(token in text for token in ("Ã", "Â", "�")):
        for source_encoding in ("latin-1", "cp1252"):
            try:
                repaired = text.encode(source_encoding).decode("utf-8")
                if repaired:
                    return repaired.strip()
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return text


def normalize_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def collect_line_parts(geometry):
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry] if geometry.length > 0 else []
    if isinstance(geometry, MultiLineString):
        return [part for part in geometry.geoms if not part.is_empty and part.length > 0]
    if hasattr(geometry, "geoms"):
        parts = []
        for child in geometry.geoms:
            parts.extend(collect_line_parts(child))
        return parts
    return []


def normalize_line_geometry(geometry):
    parts = collect_line_parts(geometry)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]

    merged = linemerge(MultiLineString(parts))
    merged_parts = collect_line_parts(merged)
    if not merged_parts:
        return MultiLineString(parts)
    if len(merged_parts) == 1:
        return merged_parts[0]
    return MultiLineString(merged_parts)


def geometry_mapping(geometry):
    return mapping(force_2d(geometry))


def load_target_contour_utm():
    payload = load_json(TARGET_CONTOUR_PATH)
    features = payload.get("features", [])
    if not features:
        raise RuntimeError("No se encontro el contorno cartografico 400 m ajustado.")

    to_utm = Transformer.from_crs(WGS84, TARGET_CRS, always_xy=True)
    geometries = [transform(to_utm.transform, force_2d(shape(feature["geometry"]))) for feature in features]
    contour_utm = unary_union(geometries).buffer(0)
    if contour_utm.is_empty:
        raise RuntimeError("El contorno cartografico 400 m ajustado esta vacio.")
    return contour_utm


def extract_source_shapefile():
    source_zip = resolve_source_zip()

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_zip) as archive:
        archive.extractall(EXTRACT_DIR)

    shp_path = next(EXTRACT_DIR.rglob("*.shp"), None)
    prj_path = next(EXTRACT_DIR.rglob("*.prj"), None)
    if shp_path is None:
        raise FileNotFoundError("No se encontro un shapefile dentro del ZIP de transporte.")
    return source_zip, shp_path, prj_path


def read_source_crs(prj_path: Path | None):
    if prj_path is None or not prj_path.exists():
        return WGS84
    wkt = prj_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not wkt:
        return WGS84
    return CRS.from_wkt(wkt)


def build_outputs():
    source_zip, shp_path, prj_path = extract_source_shapefile()
    contour_utm = load_target_contour_utm()
    source_crs = read_source_crs(prj_path)
    to_utm = Transformer.from_crs(source_crs, TARGET_CRS, always_xy=True)
    to_wgs84 = Transformer.from_crs(TARGET_CRS, WGS84, always_xy=True)

    line_features = []
    line_lengths = []
    buffer_geometries = []
    total_original_length_m = 0.0
    total_clipped_length_m = 0.0

    reader = shapefile.Reader(str(shp_path))
    source_count = len(reader)
    try:
        for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = shape_record.record.as_dict()
            geometry_src = force_2d(shape(shape_record.shape.__geo_interface__))
            geometry_utm = transform(to_utm.transform, geometry_src)
            original_length_m = float(geometry_utm.length)
            total_original_length_m += original_length_m

            clipped = geometry_utm.intersection(contour_utm)
            clipped_line = normalize_line_geometry(clipped)
            if clipped_line is None or clipped_line.is_empty:
                continue

            clipped_length_m = float(clipped_line.length)
            total_clipped_length_m += clipped_length_m

            route_id = normalize_text(record.get("Name"))
            route_name = normalize_text(record.get("Linea") or route_id or f"Ruta {index}")
            route_note = normalize_text(record.get("Snippet"))
            route_attr_length_km = normalize_float(record.get("Long_Recor"))

            properties = {
                "source_id": index,
                "codigo": route_id,
                "route_id": route_id,
                "nombre": route_name,
                "linea": route_name,
                "snippet": route_note,
                "long_recor_km_attr": round(route_attr_length_km, 6),
                "longitud_original_m": round(original_length_m, 2),
                "longitud_recortada_m": round(clipped_length_m, 2),
                "segmentos_recortados": len(collect_line_parts(clipped_line)),
                "buffer_side_m": BUFFER_SIDE_METERS,
                "buffer_total_m": BUFFER_TOTAL_METERS,
                "source_type": "transporte_intracantonal_recortado",
                "clip_reference": "contorno_cartografico_limite_plataforma_n_400m",
            }

            line_features.append(
                {
                    "type": "Feature",
                    "geometry": geometry_mapping(transform(to_wgs84.transform, clipped_line)),
                    "properties": properties,
                }
            )
            line_lengths.append(properties)
            buffer_geometries.append(clipped_line.buffer(BUFFER_SIDE_METERS))
    finally:
        reader.close()
        shutil.rmtree(EXTRACT_DIR, ignore_errors=True)

    if not line_features:
        raise RuntimeError("No se encontraron rutas de transporte dentro del contorno cartografico 400 m.")

    dissolved_buffer = unary_union(buffer_geometries).buffer(0)
    clipped_buffer = dissolved_buffer.intersection(contour_utm).buffer(0)
    if clipped_buffer.is_empty:
        raise RuntimeError("El buffer de transporte quedo vacio despues del recorte.")

    buffer_feature = {
        "type": "Feature",
        "geometry": geometry_mapping(transform(to_wgs84.transform, clipped_buffer)),
        "properties": {
            "nombre": "Buffer transporte intracantonal recortado al contorno cartografico 400 m",
            "codigo": "TRANSPORTE_INTRACANTONAL",
            "feature_count": len(line_features),
            "rutas_recortadas": len(line_features),
            "buffer_side_m": BUFFER_SIDE_METERS,
            "buffer_total_m": BUFFER_TOTAL_METERS,
            "longitud_total_original_m": round(total_original_length_m, 2),
            "longitud_total_recortada_m": round(total_clipped_length_m, 2),
            "area_generada_m2": round(clipped_buffer.area, 2),
            "area_poligono_m2": round(clipped_buffer.area, 2),
            "source_type": "transporte_intracantonal_buffer_recortado",
            "clip_reference": "contorno_cartografico_limite_plataforma_n_400m",
        },
    }

    line_features.sort(key=lambda feature: feature["properties"].get("nombre", ""))

    stats = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_zip": str(source_zip),
        "source_shapefile": shp_path.name,
        "source_crs": source_crs.to_string(),
        "clip_source": str(TARGET_CONTOUR_PATH),
        "summary": {
            "rutas_fuente": source_count,
            "rutas_recortadas": len(line_features),
            "buffer_side_m": BUFFER_SIDE_METERS,
            "buffer_total_m": BUFFER_TOTAL_METERS,
            "longitud_total_original_m": round(total_original_length_m, 2),
            "longitud_total_recortada_m": round(total_clipped_length_m, 2),
            "area_buffer_m2": round(clipped_buffer.area, 2),
        },
        "by_route": [
            {
                "codigo": item["codigo"],
                "nombre": item["nombre"],
                "snippet": item["snippet"],
                "longitud_recortada_m": item["longitud_recortada_m"],
                "segmentos_recortados": item["segmentos_recortados"],
            }
            for item in sorted(line_lengths, key=lambda item: (-item["longitud_recortada_m"], item["nombre"]))
        ],
    }

    save_json(OUTPUT_LINES_PATH, {"type": "FeatureCollection", "features": line_features})
    save_json(OUTPUT_BUFFER_PATH, {"type": "FeatureCollection", "features": [buffer_feature]})
    save_json(OUTPUT_STATS_PATH, stats)

    print("Listo.")
    print(f"Rutas recortadas: {OUTPUT_LINES_PATH}")
    print(f"Buffer 200 m lado: {OUTPUT_BUFFER_PATH}")
    print(f"Stats transporte:  {OUTPUT_STATS_PATH}")
    print(f"Rutas recortadas: {len(line_features)}")


if __name__ == "__main__":
    build_outputs()
