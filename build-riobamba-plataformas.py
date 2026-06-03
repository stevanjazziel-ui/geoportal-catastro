import json
import math
import os
import shutil
import zipfile

import shapefile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = r"C:\Users\PC\Downloads\plataformas.zip"
OUT_DIR = os.path.join(BASE_DIR, "riobamba-censo-data")
MANZANAS_PATH = os.path.join(OUT_DIR, "riobamba_manzanas.geojson")
MANZANAS_STATS_PATH = os.path.join(OUT_DIR, "riobamba_manzanas_stats.json")
PLATFORMS_GEOJSON_PATH = os.path.join(OUT_DIR, "riobamba_plataformas.geojson")
PLATFORMS_STATS_PATH = os.path.join(OUT_DIR, "riobamba_plataformas_stats.json")
EXTRACT_DIR = os.path.join(OUT_DIR, "_tmp_plataformas")

METRIC_KEYS = [
    "population_total",
    "male",
    "female",
    "age_0_14",
    "age_15_29",
    "age_30_44",
    "age_45_64",
    "age_65_plus",
]


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
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    return ring


def shape_to_polygons(shape):
    parts = list(shape.parts) + [len(shape.points)]
    rings = []

    for idx in range(len(parts) - 1):
      start = parts[idx]
      end = parts[idx + 1]
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

    return polygons


def platform_geometry_to_geojson(polygons):
    if len(polygons) == 1:
        coordinates = [polygons[0]["outer"], *polygons[0]["holes"]]
        return {"type": "Polygon", "coordinates": coordinates}

    coordinates = []
    for polygon in polygons:
        coordinates.append([polygon["outer"], *polygon["holes"]])
    return {"type": "MultiPolygon", "coordinates": coordinates}


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

    if geometry["type"] == "Polygon":
        candidate_polygons = [geometry["coordinates"]]
    else:
        candidate_polygons = geometry["coordinates"]

    for polygon in candidate_polygons:
        outer = polygon[0]
        area = abs(signed_area(outer))
        if area > best_area:
            best_area = area
            best_ring = outer

    if best_ring:
        return ring_centroid(best_ring)

    return [0.0, 0.0]


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


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def build_platform_features():
    if os.path.isdir(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(EXTRACT_DIR)

    shp_path = os.path.join(EXTRACT_DIR, "plataformas", "Plataformas_a.shp")
    reader = shapefile.Reader(shp_path)

    features = []
    for shape_record in reader.iterShapeRecords():
        record = shape_record.record.as_dict()
        polygons = shape_to_polygons(shape_record.shape)
        geometry = platform_geometry_to_geojson(polygons)
        properties = {
            "platform_id": int(record["No"]),
            "platform_name": str(record["Nombre"]).strip(),
            "area": float(record["Area"]),
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            }
        )

    features.sort(key=lambda feature: feature["properties"]["platform_id"])
    return features


def empty_stats():
    payload = {"manzanas": 0}
    for key in METRIC_KEYS:
        payload[key] = 0
    return payload


def main():
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"No se encontro el archivo: {ZIP_PATH}")
    if not os.path.exists(MANZANAS_PATH):
        raise FileNotFoundError(f"No se encontro el archivo base: {MANZANAS_PATH}")
    if not os.path.exists(MANZANAS_STATS_PATH):
        raise FileNotFoundError(f"No se encontro el archivo base: {MANZANAS_STATS_PATH}")

    platform_features = build_platform_features()
    manzanas_geo = load_json(MANZANAS_PATH)
    manzanas_stats = load_json(MANZANAS_STATS_PATH)
    by_man = manzanas_stats.get("byMan", {})

    platform_index = []
    platform_totals = {}
    for feature in platform_features:
        props = feature["properties"]
        name = props["platform_name"]
        bbox = geometry_bbox(feature["geometry"])
        platform_index.append(
            {
                "name": name,
                "bbox": bbox,
                "geometry": feature["geometry"],
            }
        )
        platform_totals[name] = {
            "platform_id": props["platform_id"],
            "platform_name": name,
            "area": props["area"],
            **empty_stats(),
        }

    man_to_platform = {}
    unassigned = empty_stats()

    for feature in manzanas_geo["features"]:
        man = str(feature["properties"]["man"])
        stat = by_man.get(man)
        if not stat:
            continue

        point = geometry_centroid(feature["geometry"])
        assigned_name = None

        for platform in platform_index:
            if not point_in_bbox(point, platform["bbox"]):
                continue
            if point_in_geojson(point, platform["geometry"]):
                assigned_name = platform["name"]
                break

        if assigned_name is None:
            unassigned["manzanas"] += 1
            for key in METRIC_KEYS:
                unassigned[key] += int(stat.get(key, 0))
            continue

        man_to_platform[man] = assigned_name
        target = platform_totals[assigned_name]
        target["manzanas"] += 1
        for key in METRIC_KEYS:
            target[key] += int(stat.get(key, 0))

    for feature in platform_features:
        props = feature["properties"]
        props.update(platform_totals[props["platform_name"]])

    summary = {
        "platforms_total": len(platform_features),
        "platforms_with_data": sum(1 for item in platform_totals.values() if item["manzanas"] > 0),
        "manzanas_assigned": sum(item["manzanas"] for item in platform_totals.values()),
        "manzanas_without_platform": unassigned["manzanas"],
    }
    for key in METRIC_KEYS:
        summary[key] = sum(item[key] for item in platform_totals.values())
    summary["population_total_with_platform"] = summary["population_total"]
    summary["population_total_without_platform"] = unassigned["population_total"]

    platforms_list = sorted(platform_totals.values(), key=lambda item: item["platform_id"])

    geojson_payload = {"type": "FeatureCollection", "features": platform_features}
    stats_payload = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source": "Plataformas + manzanas censales CPV 2022 de Riobamba",
        "summary": summary,
        "unassigned": unassigned,
        "platforms": platforms_list,
        "byName": {item["platform_name"]: item for item in platforms_list},
        "manToPlatform": man_to_platform,
    }

    with open(PLATFORMS_GEOJSON_PATH, "w", encoding="utf-8") as handle:
        json.dump(geojson_payload, handle, ensure_ascii=False)

    with open(PLATFORMS_STATS_PATH, "w", encoding="utf-8") as handle:
        json.dump(stats_payload, handle, ensure_ascii=False)

    if os.path.isdir(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)

    print("Listo.")
    print(f"GeoJSON: {PLATFORMS_GEOJSON_PATH}")
    print(f"Stats:   {PLATFORMS_STATS_PATH}")


if __name__ == "__main__":
    main()
