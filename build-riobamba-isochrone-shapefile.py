import json
import shutil
import zipfile
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
SHP_DIR = DATA_DIR / "shp"
ISOCHRONE_PATH = DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m.geojson"
MANIFEST_PATH = SHP_DIR / "manifest.json"
OUTPUT_BASENAME = "limite_isocrona_limite_plataforma_n_400m"

PRJ_WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def geometry_parts(feature):
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        parts = []
        for polygon in geometry["coordinates"]:
            parts.extend(polygon)
        return parts
    raise ValueError(f"Geometria no soportada: {geometry['type']}")


def write_zip(feature):
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = SHP_DIR / OUTPUT_BASENAME
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / OUTPUT_BASENAME
    writer = shapefile.Writer(str(shp_base), shapeType=shapefile.POLYGON)
    writer.autoBalance = 1

    writer.field("nombre", "C", size=80)
    writer.field("target", "C", size=24)
    writer.field("dist_m", "N", size=10, decimal=0)
    writer.field("src_type", "C", size=16)
    writer.field("muestras", "N", size=10, decimal=0)
    writer.field("src_nodes", "N", size=10, decimal=0)
    writer.field("snap_avg", "N", size=10, decimal=2)
    writer.field("nodos", "N", size=12, decimal=0)
    writer.field("seg_red", "N", size=12, decimal=0)
    writer.field("manz_aj", "N", size=12, decimal=0)
    writer.field("long_red", "N", size=14, decimal=2)
    writer.field("area_red", "N", size=14, decimal=2)
    writer.field("area_mz", "N", size=14, decimal=2)
    writer.field("area_fin", "N", size=14, decimal=2)
    writer.field("modo", "C", size=12)

    props = feature["properties"]
    writer.poly(geometry_parts(feature))
    writer.record(
        str(props.get("nombre", ""))[:80],
        str(props.get("target_platform", ""))[:24],
        int(props.get("distance_m", 0) or 0),
        str(props.get("source_type", ""))[:16],
        int(props.get("boundary_samples", 0) or 0),
        int(props.get("source_nodes", 0) or 0),
        float(props.get("snap_promedio_m", 0) or 0),
        int(props.get("nodos_alcanzables", 0) or 0),
        int(props.get("segmentos_red", 0) or 0),
        int(props.get("manzanas_ajustadas", 0) or 0),
        float(props.get("longitud_red_m", 0) or 0),
        float(props.get("area_poligono_red_m2", 0) or 0),
        float(props.get("area_poligono_manzanas_m2", 0) or 0),
        float(props.get("area_poligono_m2", 0) or 0),
        str(props.get("mode", ""))[:12],
    )
    writer.close()

    with open(shp_base.with_suffix(".prj"), "w", encoding="utf-8") as handle:
        handle.write(PRJ_WGS84)

    zip_path = SHP_DIR / f"{OUTPUT_BASENAME}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for extension in (".shp", ".shx", ".dbf", ".prj"):
            file_path = shp_base.with_suffix(extension)
            archive.write(file_path, arcname=file_path.name)

    shutil.rmtree(temp_dir)
    return zip_path


def update_manifest(zip_path: Path, feature_count: int):
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}
    manifest[OUTPUT_BASENAME] = {
        "file": zip_path.name,
        "count": feature_count,
        "label": "Isocrona exacta de red 400 m desde el borde de la plataforma N",
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def main():
    payload = load_json(ISOCHRONE_PATH)
    features = payload.get("features", [])
    if not features:
        raise RuntimeError("No se encontro la isocrona para exportar.")

    zip_path = write_zip(features[0])
    update_manifest(zip_path, len(features))

    print("Listo.")
    print(zip_path)


if __name__ == "__main__":
    main()
