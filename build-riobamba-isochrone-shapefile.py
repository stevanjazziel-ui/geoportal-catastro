import json
import re
import shutil
import zipfile
from pathlib import Path

import shapefile

from riobamba_categorized_isocronas_config import iter_categorized_isochrone_configs


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "riobamba-censo-data"
SHP_DIR = DATA_DIR / "shp"
MANIFEST_PATH = SHP_DIR / "manifest.json"
MANZANAS_PATH = DATA_DIR / "riobamba_manzanas.geojson"
MANZANAS_STATS_PATH = DATA_DIR / "riobamba_manzanas_stats.json"

PRJ_WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'

BASE_EXPORTS = [
    {
        "source_path": DATA_DIR / "riobamba_isocrona_plataforma_n_1000m.geojson",
        "output_basename": "limite_isocrona_plataforma_n_1000m",
        "label": "Limite externo de isocrona 1000 m desde equipamientos de la plataforma Ñ",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
        "bundle_mode": "single",
        "required": False,
    },
    {
        "source_path": DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m.geojson",
        "output_basename": "limite_isocrona_limite_plataforma_n_400m",
        "label": "Isocrona exacta de red 400 m desde el borde de la plataforma Ñ",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
        "bundle_mode": "single",
        "required": True,
    },
    {
        "source_path": DATA_DIR / "riobamba_isocrona_limite_plataforma_n_400m_ajustada_manzanas.geojson",
        "output_basename": "contorno_cartografico_limite_plataforma_n_400m",
        "label": "Contorno cartografico ajustado 400 m desde el borde de la plataforma Ñ",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
        "bundle_mode": "single",
        "required": True,
    },
    {
        "source_path": DATA_DIR / "riobamba_transporte_intracantonal_recortado_carto_400m.geojson",
        "output_basename": "rutas_transporte_intracantonal_recortadas_400m_carto",
        "label": "Rutas de transporte intracantonal recortadas al contorno cartografico 400 m",
        "shape_type": shapefile.POLYLINE,
        "geometry_mode": "line",
        "bundle_mode": "single",
        "required": False,
    },
    {
        "source_path": DATA_DIR / "riobamba_transporte_intracantonal_buffer_carto_200m.geojson",
        "output_basename": "buffer_transporte_intracantonal_200m_lado",
        "label": "Buffer de transporte intracantonal de 200 m por lado dentro del contorno 400 m",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
        "bundle_mode": "single",
        "required": False,
    },
    {
        "source_path": DATA_DIR / "riobamba_isocronas_paradas_bus.geojson",
        "output_basename": "isocronas_paradas_bus_400m",
        "label": "ZIP con shapefiles separados del borde exterior de cada isocrona de parada de bus",
        "shape_type": shapefile.POLYGON,
        "geometry_mode": "polygon",
        "bundle_mode": "per_feature",
        "required": False,
    },
    {
        "source_path": DATA_DIR / "riobamba_isocronas_paradas_bus.geojson",
        "output_basename": "puntos_inicio_isocronas_paradas_bus",
        "label": "Shapefile ZIP con los puntos de inicio de las isocronas de paradas de bus",
        "shape_type": shapefile.POINT,
        "geometry_mode": "source_point",
        "bundle_mode": "single",
        "required": False,
    },
]


def build_categorized_exports():
    exports = []
    for config in iter_categorized_isochrone_configs():
        exports.append(
            {
                "source_path": config.output_isocronas,
                "output_basename": config.shp_polygon_basename,
                "label": config.shp_polygon_label,
                "shape_type": shapefile.POLYGON,
                "geometry_mode": "polygon",
                "bundle_mode": "per_feature",
                "required": False,
            }
        )
        exports.append(
            {
                "source_path": config.output_isocronas,
                "output_basename": config.shp_start_points_basename,
                "label": config.shp_start_points_label,
                "shape_type": shapefile.POINT,
                "geometry_mode": "source_point",
                "bundle_mode": "single",
                "required": False,
            }
        )
        if config.key in {"educacion", "recreacion", "bienestar", "cultura"}:
            exports.append(
                {
                    "source_path": config.output_isocronas,
                    "output_basename": config.shp_covered_manzanas_basename,
                    "label": config.shp_covered_manzanas_label,
                    "shape_type": shapefile.POLYGON,
                    "geometry_mode": "covered_manzanas",
                    "bundle_mode": "per_feature_manzanas",
                    "required": False,
                }
            )
    return exports


def resolve_exports():
    exports = []
    for config in [*BASE_EXPORTS, *build_categorized_exports()]:
        source_path = config["source_path"]
        if source_path.exists():
            exports.append(config)
            continue
        if config.get("required", True):
            raise FileNotFoundError(f"No se encontro el archivo fuente para exportar: {source_path}")
    return exports


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sanitize_token(value):
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
    token = token.strip("_")
    return token or "sin_nombre"


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
    elif geometry_mode == "line":
        if geometry["type"] == "LineString":
            return [geometry["coordinates"]]
        if geometry["type"] == "MultiLineString":
            return geometry["coordinates"]
    elif geometry_mode == "exterior_line":
        if geometry["type"] == "Polygon":
            return [geometry["coordinates"][0]]
        if geometry["type"] == "MultiPolygon":
            return [polygon[0] for polygon in geometry["coordinates"] if polygon and polygon[0]]
    elif geometry_mode == "source_point":
        props = feature.get("properties", {})
        lon = props.get("source_lon")
        lat = props.get("source_lat")
        if lon is None or lat is None:
            raise ValueError("No se encontraron source_lon/source_lat para exportar el punto inicial.")
        return [(float(lon), float(lat))]
    raise ValueError(f"Geometria no soportada: {geometry['type']}")


def init_writer(shp_base: Path, shape_type):
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
    writer.field("pob_tot", "N", size=12, decimal=0)
    writer.field("modo", "C", size=12)
    writer.field("categor", "C", size=20)
    writer.field("codigo", "C", size=24)
    writer.field("ruta_id", "C", size=24)
    writer.field("long_orig", "N", size=14, decimal=2)
    writer.field("long_clip", "N", size=14, decimal=2)
    writer.field("buf_side", "N", size=8, decimal=0)
    writer.field("buf_total", "N", size=8, decimal=0)
    writer.field("feat_cnt", "N", size=8, decimal=0)
    writer.field("area_gen", "N", size=14, decimal=2)
    writer.field("snippet", "C", size=40)
    writer.field("src_lon", "N", size=16, decimal=8)
    writer.field("src_lat", "N", size=16, decimal=8)
    return writer


def init_manzana_writer(shp_base: Path):
    writer = shapefile.Writer(str(shp_base), shapeType=shapefile.POLYGON)
    writer.autoBalance = 1
    writer.field("man", "C", size=18)
    writer.field("iso_nom", "C", size=80)
    writer.field("iso_cod", "C", size=24)
    writer.field("categor", "C", size=20)
    writer.field("dist_m", "N", size=10, decimal=0)
    writer.field("equipam", "C", size=32)
    writer.field("pob_tot", "N", size=12, decimal=0)
    writer.field("male", "N", size=12, decimal=0)
    writer.field("female", "N", size=12, decimal=0)
    writer.field("age0_4", "N", size=12, decimal=0)
    writer.field("age5_11", "N", size=12, decimal=0)
    writer.field("age12_17", "N", size=12, decimal=0)
    writer.field("age18_29", "N", size=12, decimal=0)
    writer.field("age30_64", "N", size=12, decimal=0)
    writer.field("age65pls", "N", size=12, decimal=0)
    writer.field("src_id", "N", size=10, decimal=0)
    return writer


def write_feature_geometry(writer, feature, geometry_mode, shape_type):
    parts = geometry_parts(feature, geometry_mode=geometry_mode)
    if shape_type == shapefile.POINT:
        lon, lat = parts[0]
        writer.point(lon, lat)
    elif shape_type == shapefile.POLYLINE:
        writer.line(parts)
    else:
        writer.poly(parts)


def write_feature_record(writer, feature):
    props = feature.get("properties", {})
    writer.record(
        nombre=str(props.get("nombre", ""))[:80],
        target=str(props.get("target_platform", ""))[:24],
        dist_m=int(props.get("distance_m", 0) or 0),
        src_type=str(props.get("source_type", props.get("origin_type", "")))[:32],
        muestras=int(props.get("boundary_samples", 0) or 0),
        src_nodes=int(props.get("source_nodes", 0) or 0),
        snap_avg=float(props.get("snap_promedio_m", props.get("snap_m", 0)) or 0),
        nodos=int(props.get("nodos_alcanzables", 0) or 0),
        seg_red=int(props.get("segmentos_red", 0) or 0),
        manz_aj=int(props.get("manzanas_ajustadas", 0) or 0),
        long_red=float(props.get("longitud_red_m", 0) or 0),
        area_red=float(props.get("area_poligono_red_m2", props.get("area_poligono_exacto_m2", 0)) or 0),
        area_mz=float(props.get("area_poligono_manzanas_m2", 0) or 0),
        area_fin=float(props.get("area_poligono_m2", 0) or 0),
        pob_tot=int(props.get("population_total", 0) or 0),
        modo=str(props.get("mode", ""))[:12],
        categor=str(props.get("categoria", ""))[:20],
        codigo=str(props.get("codigo", ""))[:24],
        ruta_id=str(props.get("route_id", ""))[:24],
        long_orig=float(props.get("longitud_original_m", 0) or 0),
        long_clip=float(props.get("longitud_recortada_m", props.get("longitud_total_recortada_m", 0)) or 0),
        buf_side=int(props.get("buffer_side_m", 0) or 0),
        buf_total=int(props.get("buffer_total_m", 0) or 0),
        feat_cnt=int(props.get("feature_count", props.get("rutas_recortadas", 0)) or 0),
        area_gen=float(props.get("area_generada_m2", 0) or 0),
        snippet=str(props.get("snippet", ""))[:40],
        src_lon=float(props.get("source_lon", 0) or 0),
        src_lat=float(props.get("source_lat", 0) or 0),
    )


def finalize_writer(writer, shp_base: Path):
    writer.close()
    with open(shp_base.with_suffix(".prj"), "w", encoding="utf-8") as handle:
        handle.write(PRJ_WGS84)


def build_feature_basename(feature, index):
    props = feature.get("properties", {})
    categoria = sanitize_token(props.get("categoria", "sin_categoria")).lower()
    codigo = sanitize_token(props.get("codigo", f"{index:03d}"))
    nombre = sanitize_token(props.get("nombre", f"isocrona_{index:03d}"))[:36]
    return f"iso_{index:03d}_{categoria}_{codigo}_{nombre}"


def build_manzana_feature_basename(feature, index):
    return f"{build_feature_basename(feature, index)}_manzanas"


def load_manzana_lookup():
    manzanas_geo = load_json(MANZANAS_PATH)
    manzanas_stats = load_json(MANZANAS_STATS_PATH).get("byMan", {})
    lookup = {}

    for feature in manzanas_geo.get("features", []):
        props = feature.get("properties", {})
        man = str(props.get("man") or "").strip()
        if not man:
            continue
        merged_props = {
            **props,
            **(manzanas_stats.get(man) or {}),
        }
        lookup[man] = {
            "type": "Feature",
            "properties": merged_props,
            "geometry": feature.get("geometry"),
        }

    return lookup


def write_manzana_record(writer, manzana_feature, source_feature):
    mprops = manzana_feature.get("properties", {})
    sprops = source_feature.get("properties", {})
    writer.record(
        man=str(mprops.get("man", ""))[:18],
        iso_nom=str(sprops.get("nombre", ""))[:80],
        iso_cod=str(sprops.get("codigo", ""))[:24],
        categor=str(sprops.get("categoria", ""))[:20],
        dist_m=int(sprops.get("distance_m", 0) or 0),
        equipam=str(sprops.get("equipamien", ""))[:32],
        pob_tot=int(mprops.get("population_total", 0) or 0),
        male=int(mprops.get("male", 0) or 0),
        female=int(mprops.get("female", 0) or 0),
        age0_4=int(mprops.get("age_0_4", 0) or 0),
        age5_11=int(mprops.get("age_5_11", 0) or 0),
        age12_17=int(mprops.get("age_12_17", 0) or 0),
        age18_29=int(mprops.get("age_18_29", 0) or 0),
        age30_64=int(mprops.get("age_30_64", 0) or 0),
        age65pls=int(mprops.get("age_65_plus", 0) or 0),
        src_id=int(sprops.get("source_id", 0) or 0),
    )


def write_per_feature_manzanas_bundle(features, output_basename: str):
    temp_dir = SHP_DIR / output_basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    manzanas_by_id = load_manzana_lookup()
    written = 0

    for index, feature in enumerate(features, start=1):
        covered_ids = feature.get("properties", {}).get("covered_manzanas") or []
        covered_features = [manzanas_by_id[man_id] for man_id in covered_ids if man_id in manzanas_by_id]
        if not covered_features:
            continue

        shp_base = temp_dir / build_manzana_feature_basename(feature, index)
        writer = init_manzana_writer(shp_base)
        for manzana_feature in covered_features:
            write_feature_geometry(writer, manzana_feature, "polygon", shapefile.POLYGON)
            write_manzana_record(writer, manzana_feature, feature)
        finalize_writer(writer, shp_base)
        written += 1

    if written == 0:
        raise RuntimeError(f"No se encontraron manzanas cubiertas para exportar en {output_basename}.")

    return temp_dir


def write_single_bundle(features, output_basename: str, shape_type, geometry_mode):
    temp_dir = SHP_DIR / output_basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / output_basename
    writer = init_writer(shp_base, shape_type)
    for feature in features:
        write_feature_geometry(writer, feature, geometry_mode, shape_type)
        write_feature_record(writer, feature)
    finalize_writer(writer, shp_base)
    return temp_dir


def write_per_feature_bundle(features, output_basename: str, shape_type, geometry_mode):
    temp_dir = SHP_DIR / output_basename
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for index, feature in enumerate(features, start=1):
        shp_base = temp_dir / build_feature_basename(feature, index)
        writer = init_writer(shp_base, shape_type)
        write_feature_geometry(writer, feature, geometry_mode, shape_type)
        write_feature_record(writer, feature)
        finalize_writer(writer, shp_base)

    return temp_dir


def pack_directory(temp_dir: Path, output_basename: str):
    zip_path = SHP_DIR / f"{output_basename}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(temp_dir.iterdir()):
            archive.write(file_path, arcname=file_path.name)
    shutil.rmtree(temp_dir)
    return zip_path


def write_zip(features, output_basename: str, shape_type, geometry_mode, bundle_mode):
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    if bundle_mode == "per_feature":
        temp_dir = write_per_feature_bundle(features, output_basename, shape_type, geometry_mode)
    elif bundle_mode == "per_feature_manzanas":
        temp_dir = write_per_feature_manzanas_bundle(features, output_basename)
    else:
        temp_dir = write_single_bundle(features, output_basename, shape_type, geometry_mode)
    return pack_directory(temp_dir, output_basename)


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
        config.get("bundle_mode", "single"),
    )
    return {
        "output_basename": config["output_basename"],
        "zip_path": zip_path,
        "feature_count": len(features),
        "label": config["label"],
    }


def main():
    export_configs = resolve_exports()
    results = [build_export(config) for config in export_configs]
    update_manifest(results)

    print("Listo.")
    for result in results:
        print(result["zip_path"])


if __name__ == "__main__":
    main()
