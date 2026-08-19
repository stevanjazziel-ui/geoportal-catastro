from __future__ import annotations

import copy
import datetime as dt
import json
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PREMIO_DIR = DATA_DIR / "premio-habitat"
SHP_DIR = PREMIO_DIR / "shp"
ISOCHRONES_PATH = DATA_DIR / "riobamba-poligono-isocronas.geojson"
PRIMARY_PATH = PREMIO_DIR / "premio-habitat-nodos-principales.geojson"
SECONDARY_PATH = PREMIO_DIR / "premio-habitat-nodos-secundarios.geojson"
OUTPUT_TEMPLATE = "premio-habitat-nodos-isocrona-{distance}m.geojson"
ZIP_TEMPLATE = "premio-habitat-nodos-isocrona-{distance}m.zip"
STATS_PATH = PREMIO_DIR / "premio-habitat-nodos-isocronas-stats.json"
DISTANCES_M = (200, 500)
PRJ_WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_field_name(name: str, used_names: set[str]):
    normalized = unicodedata.normalize("NFD", str(name or ""))
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_").upper() or "FIELD"
    base_name = normalized[:10]
    candidate = base_name
    suffix = 1
    while candidate in used_names:
        suffix_text = str(suffix)
        candidate = f"{base_name[: max(0, 10 - len(suffix_text))]}{suffix_text}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def infer_field_specs(features):
    source_keys = []
    seen_keys = set()
    for feature in features:
        for key in feature.get("properties", {}).keys():
            if key not in seen_keys:
                source_keys.append(key)
                seen_keys.add(key)

    used_names = set()
    field_specs = []
    for source_key in source_keys:
        values = [
            feature.get("properties", {}).get(source_key)
            for feature in features
            if feature.get("properties", {}).get(source_key) is not None
        ]
        field_name = normalize_field_name(source_key, used_names)

        if values and all(isinstance(value, (int, float, bool)) for value in values):
            has_decimals = any(float(value) != int(float(value)) for value in values)
            field_specs.append(
                {
                    "source_key": source_key,
                    "field_name": field_name,
                    "field_type": "N",
                    "size": 18,
                    "decimal": 8 if has_decimals else 0,
                }
            )
            continue

        max_length = max((len(str(value)) for value in values), default=1)
        field_specs.append(
            {
                "source_key": source_key,
                "field_name": field_name,
                "field_type": "C",
                "size": min(max(max_length, 1), 254),
                "decimal": 0,
            }
        )

    return field_specs


def build_record(feature, field_specs):
    properties = feature.get("properties", {})
    record = []
    for spec in field_specs:
        value = properties.get(spec["source_key"])
        if spec["field_type"] == "N":
            if value is None or value == "":
                record.append(0)
            elif spec["decimal"]:
                record.append(float(value))
            else:
                record.append(int(float(value)))
        else:
            record.append("" if value is None else str(value))
    return record


def write_shapefile_zip(features, distance_m: int):
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    basename = f"premio-habitat-nodos-isocrona-{distance_m}m"
    temp_dir = SHP_DIR / basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / basename
    writer = shapefile.Writer(str(shp_base), shapeType=shapefile.POINT, encoding="utf-8")
    writer.autoBalance = 1

    field_specs = infer_field_specs(features)
    for spec in field_specs:
        writer.field(spec["field_name"], spec["field_type"], size=spec["size"], decimal=spec["decimal"])

    for feature in features:
        lon, lat = feature.get("geometry", {}).get("coordinates", [None, None])
        if lon is None or lat is None:
            continue
        writer.point(float(lon), float(lat))
        writer.record(*build_record(feature, field_specs))

    writer.close()
    shp_base.with_suffix(".prj").write_text(PRJ_WGS84, encoding="utf-8")
    shp_base.with_suffix(".cpg").write_text("UTF-8", encoding="utf-8")

    zip_path = SHP_DIR / ZIP_TEMPLATE.format(distance=distance_m)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for extension in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            file_path = shp_base.with_suffix(extension)
            archive.write(file_path, arcname=file_path.name)

    shutil.rmtree(temp_dir)
    return zip_path


def point_in_ring(point, ring):
    x, y = point
    inside = False
    last_index = len(ring) - 1

    for index, current in enumerate(ring):
        previous = ring[last_index]
        xi, yi = current
        xj, yj = previous
        intersects = ((yi > y) != (yj > y)) and (
            x < ((xj - xi) * (y - yi)) / ((yj - yi) or float.fromhex("0x1.0p-52")) + xi
        )
        if intersects:
            inside = not inside
        last_index = index

    return inside


def point_in_polygon_coordinates(point, polygon_coordinates):
    if not polygon_coordinates:
        return False

    if not point_in_ring(point, polygon_coordinates[0]):
        return False

    for ring in polygon_coordinates[1:]:
        if point_in_ring(point, ring):
            return False

    return True


def geometry_contains_point(geometry, point):
    if not geometry:
        return False

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Polygon":
        return point_in_polygon_coordinates(point, coordinates)

    if geometry_type == "MultiPolygon":
        return any(point_in_polygon_coordinates(point, polygon) for polygon in coordinates)

    return False


def build_download_feature(feature, node_group: str, distance_m: int):
    cloned = copy.deepcopy(feature)
    properties = cloned.setdefault("properties", {})
    properties["grupo_nodo"] = node_group
    properties["isocrona_m"] = distance_m
    properties["origen_descarga"] = "premio-habitat"
    return cloned


def filter_features_within_isochrone(isochrone_geometry, features, node_group: str, distance_m: int):
    selected_features = []
    for feature in features:
        coordinates = feature.get("geometry", {}).get("coordinates")
        if not isinstance(coordinates, list):
            continue
        if geometry_contains_point(isochrone_geometry, coordinates):
            selected_features.append(build_download_feature(feature, node_group, distance_m))
    return selected_features


def main():
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    isochrones = load_json(ISOCHRONES_PATH).get("features", [])
    primary_features = load_json(PRIMARY_PATH).get("features", [])
    secondary_features = load_json(SECONDARY_PATH).get("features", [])

    stats = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "riobamba-poligono-isocronas.geojson + nodos Premio Habitat",
        "distances_m": {},
    }

    for distance_m in DISTANCES_M:
        isochrone_feature = next(
            (feature for feature in isochrones if int(feature.get("properties", {}).get("distance_m", 0)) == distance_m),
            None,
        )
        if not isochrone_feature:
            raise RuntimeError(f"No se encontró la isocrona de {distance_m} m.")

        primary_selected = filter_features_within_isochrone(
            isochrone_feature.get("geometry"),
            primary_features,
            "principal",
            distance_m,
        )
        secondary_selected = filter_features_within_isochrone(
            isochrone_feature.get("geometry"),
            secondary_features,
            "secundario",
            distance_m,
        )
        combined_features = primary_selected + secondary_selected

        output_payload = {
            "type": "FeatureCollection",
            "name": f"premio_habitat_nodos_isocrona_{distance_m}m",
            "properties": {
                "isocrona_m": distance_m,
                "total_nodos": len(combined_features),
                "nodos_principales": len(primary_selected),
                "nodos_secundarios": len(secondary_selected),
            },
            "features": combined_features,
        }

        output_path = PREMIO_DIR / OUTPUT_TEMPLATE.format(distance=distance_m)
        save_json(output_path, output_payload)
        zip_path = write_shapefile_zip(combined_features, distance_m)

        stats["distances_m"][str(distance_m)] = {
            **output_payload["properties"],
            "zip_file": zip_path.name,
            "zip_path": f"shp/{zip_path.name}",
        }

    save_json(STATS_PATH, stats)
    print("Listo.")
    for distance_key, values in stats["distances_m"].items():
        print(
            f"{distance_key} m: {values['total_nodos']} nodos "
            f"({values['nodos_principales']} principales, {values['nodos_secundarios']} secundarios)"
        )


if __name__ == "__main__":
    main()
