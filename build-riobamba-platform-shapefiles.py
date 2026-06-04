import json
import shutil
import zipfile
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"
MANZANAS_STATS_PATH = DATA_DIR / "riobamba_manzanas_stats.json"
PLATFORM_STATS_PATH = DATA_DIR / "riobamba_plataformas_stats.json"
OUTPUT_DIR = DATA_DIR / "shp"

PRJ_WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'


def slugify(value: str) -> str:
    normalized = (
        value.lower()
        .replace("ñ", "enie")
        .replace("Ã±", "enie")
        .replace("ÃƒÂ±", "enie")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("Ã¡", "a")
        .replace("Ã©", "e")
        .replace("Ã­", "i")
        .replace("Ã³", "o")
        .replace("Ãº", "u")
        .replace("ÃƒÂ¡", "a")
        .replace("ÃƒÂ©", "e")
        .replace("ÃƒÂ­", "i")
        .replace("ÃƒÂ³", "o")
        .replace("ÃƒÂº", "u")
    )
    slug = []
    prev_sep = False
    for char in normalized:
        if char.isalnum():
            slug.append(char)
            prev_sep = False
        elif not prev_sep:
            slug.append("_")
            prev_sep = True
    result = "".join(slug).strip("_")
    return result or "seleccion"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def feature_parts(feature):
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]

    if geometry["type"] == "MultiPolygon":
        parts = []
        for polygon in geometry["coordinates"]:
            parts.extend(polygon)
        return parts

    raise ValueError(f"Geometria no soportada: {geometry['type']}")


def build_record(feature):
    props = feature["properties"]
    return [
        str(props["man"]),
        str(props["platform_name"] or "SIN_PLAT"),
        int(props["population_total"]),
        int(props["male"]),
        int(props["female"]),
        int(props["age_0_4"]),
        int(props["age_5_11"]),
        int(props["age_12_17"]),
        int(props["age_18_29"]),
        int(props["age_30_64"]),
        int(props["age_65_plus"]),
    ]


def write_shapefile_zip(features, basename: str):
    temp_dir = OUTPUT_DIR / basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / basename
    writer = shapefile.Writer(str(shp_base), shapeType=shapefile.POLYGON)
    writer.autoBalance = 1

    writer.field("manzana", "C", size=24)
    writer.field("plataforma", "C", size=20)
    writer.field("pob_total", "N", size=12, decimal=0)
    writer.field("hombres", "N", size=12, decimal=0)
    writer.field("mujeres", "N", size=12, decimal=0)
    writer.field("edad0_4", "N", size=12, decimal=0)
    writer.field("edad5_11", "N", size=12, decimal=0)
    writer.field("edad12_17", "N", size=12, decimal=0)
    writer.field("edad18_29", "N", size=12, decimal=0)
    writer.field("edad30_64", "N", size=12, decimal=0)
    writer.field("edad65mas", "N", size=12, decimal=0)

    for feature in features:
        writer.poly(feature_parts(feature))
        writer.record(*build_record(feature))

    writer.close()

    prj_path = shp_base.with_suffix(".prj")
    with open(prj_path, "w", encoding="utf-8") as handle:
        handle.write(PRJ_WGS84)

    zip_path = OUTPUT_DIR / f"{basename}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for extension in (".shp", ".shx", ".dbf", ".prj"):
            file_path = shp_base.with_suffix(extension)
            archive.write(file_path, arcname=file_path.name)

    shutil.rmtree(temp_dir)
    return zip_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geo = load_json(MANZANAS_PATH)
    stats = load_json(MANZANAS_STATS_PATH)
    platform_stats = load_json(PLATFORM_STATS_PATH)

    by_man = stats.get("byMan", {})
    man_to_platform = platform_stats.get("manToPlatform", {})

    joined_features = []
    for feature in geo["features"]:
        man = feature["properties"]["man"]
        stat = by_man.get(man)
        if not stat:
            continue

        joined_features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    **feature["properties"],
                    **stat,
                    "platform_name": man_to_platform.get(man),
                },
            }
        )

    groups = {
        "riobamba_todas_las_manzanas": joined_features,
        "riobamba_fuera_de_plataformas": [
            feature for feature in joined_features if feature["properties"]["platform_name"] is None
        ],
    }

    for platform_name in platform_stats.get("byName", {}).keys():
        groups[slugify(platform_name)] = [
            feature
            for feature in joined_features
            if feature["properties"]["platform_name"] == platform_name
        ]

    manifest = {}
    for basename, features in groups.items():
        if not features:
            continue
        zip_path = write_shapefile_zip(features, basename)
        manifest[basename] = {
            "file": zip_path.name,
            "count": len(features),
        }

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    print("Listo.")
    print(f"Carpeta: {OUTPUT_DIR}")
    print(f"Archivos: {len(manifest)}")


if __name__ == "__main__":
    main()
