import collections
import json
import math
import os
import shutil
import zipfile
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
ZIP_PATH = Path(r"E:\Riobamba\equipamientos\ale_equipamientos.zip")
DATA_DIR = BASE_DIR / "riobamba-censo-data"
GEOJSON_PATH = DATA_DIR / "riobamba_equipamientos.geojson"
STATS_PATH = DATA_DIR / "riobamba_equipamientos_stats.json"
EXTRACT_DIR = DATA_DIR / "_tmp_equipamientos"


def utm17s_to_lonlat(easting, northing):
    a = 6378137.0
    ecc_squared = 0.0066943799901413165
    k0 = 0.9996
    ecc_prime_squared = ecc_squared / (1 - ecc_squared)

    x = easting - 500000.0
    y = northing - 10000000.0

    m = y / k0
    mu = m / (
        a
        * (
            1
            - ecc_squared / 4
            - 3 * ecc_squared * ecc_squared / 64
            - 5 * ecc_squared**3 / 256
        )
    )

    e1 = (1 - math.sqrt(1 - ecc_squared)) / (1 + math.sqrt(1 - ecc_squared))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1 * e1 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512

    fp = (
        mu
        + j1 * math.sin(2 * mu)
        + j2 * math.sin(4 * mu)
        + j3 * math.sin(6 * mu)
        + j4 * math.sin(8 * mu)
    )

    sin_fp = math.sin(fp)
    cos_fp = math.cos(fp)
    tan_fp = math.tan(fp)

    c1 = ecc_prime_squared * cos_fp * cos_fp
    t1 = tan_fp * tan_fp
    n1 = a / math.sqrt(1 - ecc_squared * sin_fp * sin_fp)
    r1 = a * (1 - ecc_squared) / ((1 - ecc_squared * sin_fp * sin_fp) ** 1.5)
    d = x / (n1 * k0)

    lat = fp - (n1 * tan_fp / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ecc_prime_squared) * d**4 / 24
        + (
            61
            + 90 * t1
            + 298 * c1
            + 45 * t1 * t1
            - 252 * ecc_prime_squared
            - 3 * c1 * c1
        )
        * d**6
        / 720
    )

    lon_origin = -81.0
    lon = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ecc_prime_squared + 24 * t1 * t1)
        * d**5
        / 120
    ) / cos_fp

    return [lon_origin + math.degrees(lon), math.degrees(lat)]


def signed_area(ring):
    area = 0.0
    for idx in range(len(ring) - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def close_ring(ring):
    if ring and ring[0] != ring[-1]:
        return ring + [ring[0]]
    return ring


def shape_to_geojson(shape):
    parts = list(shape.parts) + [len(shape.points)]
    rings = []

    for index in range(len(parts) - 1):
        start = parts[index]
        end = parts[index + 1]
        ring = [utm17s_to_lonlat(x, y) for x, y in shape.points[start:end]]
        ring = close_ring(ring)
        if len(ring) >= 4:
            rings.append(ring)

    polygons = []
    current = None

    for ring in rings:
        area = signed_area(ring)
        if area < 0 or current is None:
            current = {"outer": ring, "holes": []}
            polygons.append(current)
        else:
            current["holes"].append(ring)

    if len(polygons) == 1:
        return {
            "type": "Polygon",
            "coordinates": [polygons[0]["outer"], *polygons[0]["holes"]],
        }

    return {
        "type": "MultiPolygon",
        "coordinates": [[polygon["outer"], *polygon["holes"]] for polygon in polygons],
    }


def main():
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {ZIP_PATH}")

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(EXTRACT_DIR)

    shp_path = EXTRACT_DIR / "ale_equipamientos" / "equipamientos.shp"
    reader = shapefile.Reader(str(shp_path))

    try:
        features = []
        category_counter = collections.Counter()

        for shape_record in reader.iterShapeRecords():
            record = shape_record.record.as_dict()
            category = str(record.get("Equipamien", "")).strip()
            name = str(record.get("Nombre_Equ", "")).strip()
            code = str(record.get("codigo", "")).strip()

            category_counter[category] += 1

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "objectid": int(record.get("OBJECTID", 0) or 0),
                        "codigo": code,
                        "equipamien": category,
                        "categoria": category,
                        "nombre": name,
                        "shape_area": float(record.get("Shape_Area", 0) or 0),
                        "shape_leng": float(record.get("Shape_Leng", 0) or 0),
                    },
                    "geometry": shape_to_geojson(shape_record.shape),
                }
            )
    finally:
        reader.close()

    payload = {"type": "FeatureCollection", "features": features}
    stats = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source": str(ZIP_PATH),
        "summary": {
            "total_equipamientos": len(features),
            "tipos_equipamien": len(category_counter),
            "categorias": len(category_counter),
        },
        "byEquipamien": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
        "byCategory": dict(sorted(category_counter.items(), key=lambda item: (-item[1], item[0]))),
    }

    with open(GEOJSON_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)

    with open(STATS_PATH, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False)

    shutil.rmtree(EXTRACT_DIR)
    print("Listo.")
    print(f"GeoJSON: {GEOJSON_PATH}")
    print(f"Stats:   {STATS_PATH}")


if __name__ == "__main__":
    main()
