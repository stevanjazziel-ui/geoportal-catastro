import collections
import json
import shutil
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
SOURCE_ZIP = Path(r"E:\Riobamba\equipamientos\levantamiento_entorno.zip")
DATA_DIR = BASE_DIR / "riobamba-censo-data"
OUTPUT_GEOJSON = DATA_DIR / "riobamba_entorno_publico.geojson"
OUTPUT_STATS = DATA_DIR / "riobamba_entorno_publico_stats.json"
EXTRACT_DIR = DATA_DIR / "_tmp_levantamiento_entorno"


def normalize_text(value):
    return str(value or "").strip()


def normalized_key(value):
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def is_public_record(record):
    return normalized_key(record.get("tipo_equip")) == "publico"


def main():
    if not SOURCE_ZIP.exists():
        raise FileNotFoundError(f"No se encontro el archivo fuente: {SOURCE_ZIP}")

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        archive.extractall(EXTRACT_DIR)

    shp_path = next(EXTRACT_DIR.rglob("*.shp"), None)
    if shp_path is None:
        raise FileNotFoundError("No se encontro un shapefile dentro de levantamiento_entorno.zip")

    reader = shapefile.Reader(str(shp_path))
    try:
        features = []
        by_tipo = collections.Counter()
        by_elemento = collections.Counter()
        by_plataforma = collections.Counter()

        for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = shape_record.record.as_dict()
            if not is_public_record(record):
                continue

            point = shape_record.shape.points[0] if shape_record.shape.points else None
            if point is None:
                continue

            tipo_eleme = normalize_text(record.get("tipo_eleme")) or "Sin clasificar"
            elemento = normalize_text(record.get("elemento")) or "Sin elemento"
            plataforma = normalize_text(record.get("plataforma"))
            nombre_equ = normalize_text(record.get("nombre_equ"))
            nombre_ins = normalize_text(record.get("nombre_ins"))
            estado = normalize_text(record.get("estado"))
            parroquia = normalize_text(record.get("parroquia_"))
            tipologia = normalize_text(record.get("tipologia"))
            observacion = normalize_text(record.get("observacio"))
            globalid = normalize_text(record.get("globalid"))

            by_tipo[tipo_eleme] += 1
            by_elemento[elemento] += 1
            by_plataforma[plataforma or "SIN_PLATAFORMA"] += 1

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "source_id": index,
                        "globalid": globalid,
                        "codigo": globalid[-8:] if globalid else f"PUB_{index:04d}",
                        "tipo_eleme": tipo_eleme,
                        "elemento": elemento,
                        "platform_name": plataforma or None,
                        "plataforma": plataforma or None,
                        "parroquia": parroquia,
                        "estado": estado,
                        "nombre_ins": nombre_ins,
                        "tipo_equip": normalize_text(record.get("tipo_equip")),
                        "nombre_equ": nombre_equ,
                        "tipologia": tipologia,
                        "observacion": observacion,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(point[0]), float(point[1])],
                    },
                }
            )
    finally:
        reader.close()
        shutil.rmtree(EXTRACT_DIR, ignore_errors=True)

    payload = {"type": "FeatureCollection", "features": features}
    stats = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_zip": str(SOURCE_ZIP),
        "summary": {
            "total_publicos": len(features),
            "tipos_principales": len(by_tipo),
            "elementos_distintos": len(by_elemento),
            "plataformas_con_puntos": len([key for key in by_plataforma if key != "SIN_PLATAFORMA"]),
        },
        "byTipoEleme": dict(sorted(by_tipo.items(), key=lambda item: (-item[1], item[0]))),
        "byElemento": dict(sorted(by_elemento.items(), key=lambda item: (-item[1], item[0]))),
        "byPlataforma": dict(sorted(by_plataforma.items(), key=lambda item: (-item[1], item[0]))),
    }

    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    with open(OUTPUT_STATS, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    print("Listo.")
    print(f"GeoJSON: {OUTPUT_GEOJSON}")
    print(f"Stats:   {OUTPUT_STATS}")


if __name__ == "__main__":
    main()
