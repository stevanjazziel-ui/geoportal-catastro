from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR.parent / "premio habitat" / "extracted"
SOURCE_SHAPE_DIR = SOURCE_DIR / "Shp PREMIO HABITAT"
SOURCE_MDB = SOURCE_DIR / "boulevares_y_conexiones" / "GEODATABASE ENTREGABLE 4" / "ENTREGABLE 4-RIOBAMBA.mdb"
OUTPUT_DIR = BASE_DIR / "data" / "premio-habitat"
TEMP_DIR = OUTPUT_DIR / "_tmp"
OGR2OGR = Path(r"C:\Program Files\QGIS 3.40.10\bin\ogr2ogr.exe")


LAYER_SPECS = [
    {
        "key": "poligono_intervencion",
        "label": "Poligono de intervencion",
        "output": "premio-habitat-poligono-intervencion.geojson",
        "source": SOURCE_SHAPE_DIR / "Polígono de Intervención.shp",
        "open_options": ["-oo", "ENCODING=CP1252"],
    },
    {
        "key": "nodos_principales",
        "label": "Nodos principales",
        "output": "premio-habitat-nodos-principales.geojson",
        "source": SOURCE_SHAPE_DIR / "Nodos Principales.shp",
        "open_options": ["-oo", "ENCODING=CP1252"],
    },
    {
        "key": "nodos_secundarios",
        "label": "Nodos secundarios",
        "output": "premio-habitat-nodos-secundarios.geojson",
        "source": SOURCE_SHAPE_DIR / "NODOS SECUNDARIOS .shp",
        "open_options": ["-oo", "ENCODING=CP1252"],
    },
    {
        "key": "boulevares",
        "label": "Boulevares",
        "output": "premio-habitat-boulevares.geojson",
        "source": SOURCE_MDB,
        "layer_name": "SISTEMA_DE_CORREDORES",
        "open_options": [],
    },
    {
        "key": "conexiones",
        "label": "Conexiones",
        "output": "premio-habitat-conexiones.geojson",
        "source": SOURCE_MDB,
        "layer_name": "CONECTORES_SECUNDARIOS",
        "open_options": [],
    },
]


def fix_mojibake(value):
    if isinstance(value, dict):
        return {fix_mojibake(key): fix_mojibake(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [fix_mojibake(item) for item in value]
    if isinstance(value, str):
        current = value
        for _ in range(4):
            repaired = current
            for encoding_name in ("cp1252", "latin1"):
                try:
                    candidate = current.encode(encoding_name).decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
                if candidate != current:
                    repaired = candidate
                    break
            if repaired == current:
                break
            current = repaired
        return current
    return value


def iter_coords(geometry):
    if geometry is None:
        return
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        yield coordinates
        return
    if geometry_type in {"MultiPoint", "LineString"}:
        for point in coordinates:
            yield point
        return
    if geometry_type in {"MultiLineString", "Polygon"}:
        for ring in coordinates:
            for point in ring:
                yield point
        return
    if geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for point in ring:
                    yield point


def collect_bounds(features):
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    has_points = False

    for feature in features:
        for lon, lat in iter_coords(feature.get("geometry")):
            has_points = True
            min_lon = min(min_lon, lon)
            min_lat = min(min_lat, lat)
            max_lon = max(max_lon, lon)
            max_lat = max(max_lat, lat)

    if not has_points:
        return None

    return [round(min_lon, 6), round(min_lat, 6), round(max_lon, 6), round(max_lat, 6)]


def run_ogr2ogr(source_path: Path, output_path: Path, layer_name: str | None, open_options: list[str]):
    if output_path.exists():
        output_path.unlink()

    command = [
        str(OGR2OGR),
        "-f",
        "GeoJSON",
        *open_options,
        "-t_srs",
        "EPSG:4326",
        str(output_path),
        str(source_path),
    ]
    if layer_name:
        command.append(layer_name)

    subprocess.run(command, check=True)


def load_and_normalize_geojson(path: Path):
    raw_text = path.read_text(encoding="latin1")
    payload = json.loads(raw_text)
    payload = fix_mojibake(payload)
    payload.pop("crs", None)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def summarize_layer(spec, payload):
    features = payload.get("features", [])
    length_fields = ("Shape_Length", "Shape_Leng")
    total_length = 0.0
    for feature in features:
        properties = feature.get("properties", {})
        for field_name in length_fields:
            value = properties.get(field_name)
            if isinstance(value, (int, float)):
                total_length += float(value)
                break

    return {
        "key": spec["key"],
        "label": spec["label"],
        "feature_count": len(features),
        "bounds": collect_bounds(features),
        "line_length_m": round(total_length, 2) if total_length else 0,
        "output": spec["output"],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    layer_summaries = {}
    all_features = []

    for spec in LAYER_SPECS:
        temp_output = TEMP_DIR / spec["output"]
        final_output = OUTPUT_DIR / spec["output"]
        run_ogr2ogr(spec["source"], temp_output, spec.get("layer_name"), spec.get("open_options", []))
        payload = load_and_normalize_geojson(temp_output)
        final_output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        layer_summaries[spec["key"]] = summarize_layer(spec, payload)
        all_features.extend(payload.get("features", []))

    metadata = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_crs": "EPSG:32717",
        "target_crs": "EPSG:4326",
        "bounds": collect_bounds(all_features),
        "layers": layer_summaries,
    }

    metadata_path = OUTPUT_DIR / "premio-habitat-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    print("Listo.")
    for summary in layer_summaries.values():
        line_length = summary["line_length_m"]
        suffix = f", longitud {line_length} m" if line_length else ""
        print(f"{summary['label']}: {summary['feature_count']} entidades{suffix}")


if __name__ == "__main__":
    main()
