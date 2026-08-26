import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
SOURCE_SHP = Path(r"C:\Users\PC\Documents\riobamba\CDIS Y WAWATECA\CDIS_Y_WAWATECA.shp")
PLATFORMS_GEOJSON_PATH = DATA_DIR / "riobamba_plataformas.geojson"
GEOJSON_PATH = DATA_DIR / "riobamba_cdis_wawateca.geojson"
STATS_PATH = DATA_DIR / "riobamba_cdis_wawateca_stats.json"
BUNDLE_PATH = DATA_DIR / "riobamba_cdis_wawateca_bundle.js"


def repair_text(value):
    return (
        str(value or "")
        .replace("Ã¡", "á")
        .replace("Ã©", "é")
        .replace("Ã­", "í")
        .replace("Ã³", "ó")
        .replace("Ãº", "ú")
        .replace("Ã±", "ñ")
        .replace("Ã", "Á")
        .replace("Ã‰", "É")
        .replace("Ã", "Í")
        .replace("Ã“", "Ó")
        .replace("Ãš", "Ú")
        .replace("Ã‘", "Ñ")
        .replace("�", "Ñ")
        .strip()
    )


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


def ring_centroid(ring):
    area = signed_area(ring)
    if abs(area) < 1e-12:
        xs = [point[0] for point in ring[:-1]]
        ys = [point[1] for point in ring[:-1]]
        return [sum(xs) / len(xs), sum(ys) / len(ys)]

    factor = 0.0
    cx = 0.0
    cy = 0.0

    for idx in range(len(ring) - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        cross = x1 * y2 - x2 * y1
        factor += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    factor *= 0.5
    cx /= 6 * factor
    cy /= 6 * factor
    return [cx, cy]


def geometry_centroid(geometry):
    best_ring = None
    best_area = 0.0
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]

    for polygon in polygons:
        outer = polygon[0]
        area = abs(signed_area(outer))
        if area > best_area:
            best_area = area
            best_ring = outer

    return ring_centroid(best_ring) if best_ring else [0.0, 0.0]


def geometry_bbox(geometry):
    xs = []
    ys = []
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        for ring in polygon:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


def point_in_bbox(point, bbox):
    x, y = point
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def point_in_ring(point, ring):
    inside = False
    x, y = point
    for idx in range(len(ring) - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-18) + x1
        )
        if intersects:
            inside = not inside
    return inside


def point_in_geojson(point, geometry):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        if point_in_ring(point, polygon[0]):
            if any(point_in_ring(point, hole) for hole in polygon[1:]):
                continue
            return True
    return False


def distance(point_a, point_b):
    return math.dist(point_a, point_b)


def load_platforms():
    with open(PLATFORMS_GEOJSON_PATH, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    platforms = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry")
        properties = dict(feature.get("properties") or {})
        if not geometry:
            continue

        platform_name = repair_text(properties.get("platform_name") or properties.get("name"))
        properties["platform_name"] = platform_name

        platforms.append(
            {
                "feature": {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": geometry,
                },
                "name": platform_name,
                "geometry": geometry,
                "bbox": geometry_bbox(geometry),
                "centroid": geometry_centroid(geometry),
            }
        )

    return platforms


def assign_platform(point, platforms):
    for platform in platforms:
        if point_in_bbox(point, platform["bbox"]) and point_in_geojson(point, platform["geometry"]):
            return platform["name"], "polygon"

    nearest = min(platforms, key=lambda platform: distance(point, platform["centroid"]))
    return nearest["name"], "nearest_platform"


def sort_key(feature):
    properties = feature["properties"]
    return (
        repair_text(properties.get("tipo")),
        repair_text(properties.get("platform_name")),
        repair_text(properties.get("nombre")),
    )


def build_stats(features):
    summary = {
        "points_total": len(features),
        "platforms_with_points": len({feature["properties"]["platform_name"] for feature in features}),
        "ninos_total": 0,
        "assigned_by_polygon": 0,
        "assigned_by_nearest_platform": 0,
    }
    by_type = defaultdict(lambda: {"points": 0, "ninos": 0})
    by_platform = defaultdict(
        lambda: {
            "points": 0,
            "ninos": 0,
            "cdi_points": 0,
            "cdi_ninos": 0,
            "wawateca_points": 0,
            "wawateca_ninos": 0,
            "assigned_by_nearest_platform": 0,
        }
    )

    for feature in features:
        properties = feature["properties"]
        tipo = repair_text(properties["tipo"])
        platform_name = repair_text(properties["platform_name"])
        ninos = int(properties["ninos"] or 0)
        assignment_method = properties["platform_assignment_method"]

        summary["ninos_total"] += ninos
        summary[f"assigned_by_{assignment_method}"] += 1

        by_type[tipo]["points"] += 1
        by_type[tipo]["ninos"] += ninos

        platform_entry = by_platform[platform_name]
        platform_entry["points"] += 1
        platform_entry["ninos"] += ninos

        if tipo.lower() == "cdi":
            platform_entry["cdi_points"] += 1
            platform_entry["cdi_ninos"] += ninos
        else:
            platform_entry["wawateca_points"] += 1
            platform_entry["wawateca_ninos"] += ninos

        if assignment_method == "nearest_platform":
            platform_entry["assigned_by_nearest_platform"] += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(SOURCE_SHP),
        "summary": summary,
        "byType": dict(sorted(by_type.items())),
        "byPlatform": dict(sorted(by_platform.items())),
    }


def main():
    if not SOURCE_SHP.exists():
        raise FileNotFoundError(f"No se encontro el shapefile fuente: {SOURCE_SHP}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    platforms = load_platforms()
    platform_lookup = {platform["name"]: platform["feature"] for platform in platforms}

    reader = shapefile.Reader(str(SOURCE_SHP), encoding="utf-8")

    try:
        features = []
        used_platform_names = set()

        for shape_record in reader.iterShapeRecords():
            record = shape_record.record.as_dict()
            point = utm17s_to_lonlat(*shape_record.shape.points[0])
            platform_name, assignment_method = assign_platform(point, platforms)
            used_platform_names.add(platform_name)

            tipo = repair_text(record.get("TIPO"))
            source_id = int(record.get("ID") or 0)
            ninos = int(record.get("NINOS") or 0)
            nombre = repair_text(record.get("NOMBRE"))

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "feature_id": f"{tipo.upper()}-{source_id:03d}",
                        "source_id": source_id,
                        "nombre": nombre,
                        "tipo": tipo,
                        "ninos": ninos,
                        "este_x": float(record.get("ESTE_X") or 0),
                        "norte_y": float(record.get("NORTE_Y") or 0),
                        "platform_name": platform_name,
                        "platform_assignment_method": assignment_method,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": point,
                    },
                }
            )
    finally:
        reader.close()

    features.sort(key=sort_key)
    points_geojson = {"type": "FeatureCollection", "features": features}
    stats = build_stats(features)

    platform_features = [
        {
            "type": "Feature",
            "properties": dict(platform_lookup[name]["properties"]),
            "geometry": platform_lookup[name]["geometry"],
        }
        for name in sorted(used_platform_names)
    ]
    platforms_geojson = {"type": "FeatureCollection", "features": platform_features}

    bundle = {
        "generated_at": stats["generated_at"],
        "source": stats["source"],
        "points": points_geojson,
        "platforms": platforms_geojson,
        "stats": stats,
    }

    with open(GEOJSON_PATH, "w", encoding="utf-8") as handle:
        json.dump(points_geojson, handle, ensure_ascii=False)

    with open(STATS_PATH, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False)

    with open(BUNDLE_PATH, "w", encoding="utf-8") as handle:
        handle.write("window.RIOBAMBA_CDIS_WAWATECA_DATA = ")
        json.dump(bundle, handle, ensure_ascii=False)
        handle.write(";\n")

    print("Listo.")
    print(f"GeoJSON: {GEOJSON_PATH}")
    print(f"Stats:   {STATS_PATH}")
    print(f"Bundle:  {BUNDLE_PATH}")


if __name__ == "__main__":
    main()
