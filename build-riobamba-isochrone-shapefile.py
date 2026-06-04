import json
import shutil
import zipfile
from pathlib import Path

import shapefile


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
SHP_DIR = DATA_DIR / "shp"
MANIFEST_PATH = SHP_DIR / "manifest.json"

PRJ_WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'

EXPORTS = [
    {
        "source_path": DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m.geojson",
        "output_basename": "limite_isocrona_limite_plataforma_n_400m",
        "label": "Isocrona exacta de red 400 m desde el borde de la plataforma Ñ",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
    },
    {
        "source_path": DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_ajustada_manzanas.geojson",
        "output_basename": "contorno_cartografico_limite_plataforma_n_400m",
        "label": "Contorno cartografico ajustado 400 m desde el borde de la plataforma Ñ",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
    },
    {
        "source_path": DATA_DIR / "riobamba_isocronas_educacion_categorizada.geojson",
        "output_basename": "isocronas_educacion_categorizada_manzanas",
        "label": "Bordes exteriores separados de isocronas de educacion ajustadas a manzanas censales",
        "shape_type": shapefile.POLYLINE,
        "geometry_mode": "exterior_line",
    },
]


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def geometry_parts(feature, geometry_mode="polygon"):
    geometry = feature["geometry"]
    if geometry_mode == "polygon":
        if geometry["type"] == "Polygon":
            return geometry["coordinates"]
        if geometry["type"] == "MultiPolygon":
            parts = []
            for polygon in geometry["coordinates"]:
                parts.extend(polygon)
            return parts
    elif geometry_mode == "exterior_line":
        if geometry["type"] == "Polygon":
            return [geometry["coordinates"][0]]
        if geometry["type"] == "MultiPolygon":
            return [polygon[0] for polygon in geometry["coordinates"] if polygon and polygon[0]]
    raise ValueError(f"Geometria no soportada: {geometry['type']}")


def write_feature(writer, feature, geometry_mode, shape_type):
    parts = geometry_parts(feature, geometry_mode=geometry_mode)
    if shape_type == shapefile.POLYLINE:
        writer.line(parts)
    else:
        writer.poly(parts)


def write_zip(features, output_basename: str, shape_type, geometry_mode):
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = SHP_DIR / output_basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / output_basename
    writer = shapefile.Writer(str(shp_base), shapeType=shape_type)
    writer.autoBalance = 1

    writer.field("nombre", "C", size=80)
    writer.field("target", "C", size=24)
    writer.field("dist_m", "N", size=10, decimal=0)
    writer.field("src_type", "C", size=32)
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
    writer.field("categor", "C", size=20)
    writer.field("codigo", "C", size=24)

    for feature in features:
        props = feature.get("properties", {})
        write_feature(writer, feature, geometry_mode, shape_type)
        writer.record(
            str(props.get("nombre", ""))[:80],
            str(props.get("target_platform", ""))[:24],
            int(props.get("distance_m", 0) or 0),
            str(props.get("source_type", props.get("origin_type", "")))[:32],
            int(props.get("boundary_samples", 0) or 0),
            int(props.get("source_nodes", 0) or 0),
            float(props.get("snap_promedio_m", props.get("snap_m", 0)) or 0),
            int(props.get("nodos_alcanzables", 0) or 0),
            int(props.get("segmentos_red", 0) or 0),
            int(props.get("manzanas_ajustadas", 0) or 0),
            float(props.get("longitud_red_m", 0) or 0),
            float(props.get("area_poligono_red_m2", props.get("area_poligono_exacto_m2", 0)) or 0),
            float(props.get("area_poligono_manzanas_m2", 0) or 0),
            float(props.get("area_poligono_m2", 0) or 0),
            str(props.get("mode", ""))[:12],
            str(props.get("categoria", ""))[:20],
            str(props.get("codigo", ""))[:24],
        )
    writer.close()

    with open(shp_base.with_suffix(".prj"), "w", encoding="utf-8") as handle:
        handle.write(PRJ_WGS84)

    zip_path = SHP_DIR / f"{output_basename}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for extension in (".shp", ".shx", ".dbf", ".prj"):
            file_path = shp_base.with_suffix(extension)
            archive.write(file_path, arcname=file_path.name)

    shutil.rmtree(temp_dir)
    return zip_path


def update_manifest(entries):
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}
    for entry in entries:
        manifest[entry["output_basename"]] = {
            "file": entry["zip_path"].name,
            "count": entry["feature_count"],
            "label": entry["label"],
        }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def build_export(config):
    payload = load_json(config["source_path"])
    features = payload.get("features", [])
    if not features:
        raise RuntimeError(f"No se encontro geometria para exportar en {config['source_path'].name}.")

    zip_path = write_zip(
        features,
        config["output_basename"],
        config.get("shape_type", shapefile.POLYGON),
        config.get("geometry_mode", "polygon"),
    )
    return {
        "output_basename": config["output_basename"],
        "zip_path": zip_path,
        "feature_count": len(features),
        "label": config["label"],
    }


def main():
    results = [build_export(config) for config in EXPORTS]
    update_manifest(results)

    print("Listo.")
    for result in results:
        print(result["zip_path"])


if __name__ == "__main__":
    main()
