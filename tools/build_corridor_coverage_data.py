"""Build exact 200 m corridor coverage data for the local visor module."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/seguridad-riobamba/REUBICACION_POL24_20261007_B"
OUT = PACKAGE / "CORRIDOR_COVERAGE_200M.json"
METRIC_CRS = "EPSG:32717"
VISUAL_CRS = "EPSG:4326"
RADIUS_M = 200
TO_VISUAL = Transformer.from_crs(METRIC_CRS, VISUAL_CRS, always_xy=True).transform
CORRIDOR_ORDER = [
    "BOULEVARD_MACAJI_BELLAVISTA",
    "ANILLO_VIAL",
    "CICLOVIAS",
    "QUEBRADA_LAS_ABRAS",
]
CORRIDOR_NAMES = {
    "BOULEVARD_MACAJI_BELLAVISTA": "Macají–Bellavista",
    "ANILLO_VIAL": "Anillo Vial",
    "CICLOVIAS": "Ciclovías",
    "QUEBRADA_LAS_ABRAS": "Quebrada Las Abras",
}
GROUP_NAMES = {"existing": "103 existentes", "municipal": "50 municipales", "police": "30 Policía"}


def visual_geometry(geometry):
    return mapping(geometry.to_crs(VISUAL_CRS) if hasattr(geometry, "to_crs") else geometry)


def endpoint_pair(line):
    coords = list(line.coords)
    return coords[0], coords[-1]


def line_features(geometry, corridor, kind, prefix, cameras=None):
    if geometry.is_empty:
        return []
    parts = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
    features = []
    for index, part in enumerate(parts, 1):
        if part.length <= 0.01:
            continue
        start, end = endpoint_pair(part)
        nearest = None
        if cameras:
            candidate = min(cameras, key=lambda camera: camera["point"].distance(part))
            nearest = {
                "id": candidate["props"].get("ID_CAMARA") or candidate["props"].get("ID_PROPUESTA") or candidate["props"].get("ID"),
                "distanceM": round(float(candidate["point"].distance(part)), 3),
            }
        features.append({
            "type": "Feature",
            "properties": {
                "ID": f"{prefix}-{index:03d}",
                "CORREDOR": corridor,
                "TIPO": kind,
                "LONGITUD_M": round(float(part.length), 3),
                "INICIO_X": round(float(start[0]), 3),
                "INICIO_Y": round(float(start[1]), 3),
                "FIN_X": round(float(end[0]), 3),
                "FIN_Y": round(float(end[1]), 3),
                "CAMARA_MAS_CERCANA": nearest["id"] if nearest else None,
                "DISTANCIA_CAMARA_M": nearest["distanceM"] if nearest else None,
            },
                "geometry": mapping(transform(TO_VISUAL, part)),
        })
    return features


def camera_rows(path, group):
    frame = gpd.read_file(PACKAGE / path).to_crs(METRIC_CRS)
    rows = []
    for index, row in frame.iterrows():
        props = {str(k): (None if row[k] != row[k] else row[k]) for k in frame.columns if k != "geometry"}
        point = row.geometry
        rows.append({"group": group, "props": props, "point": point})
    return rows


def feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def main():
    corridors = gpd.read_file(PACKAGE / "CORREDORES.geojson").to_crs(METRIC_CRS)
    corridors = {
        row.CORREDOR: row.geometry
        for _, row in corridors.iterrows()
        if row.CORREDOR in CORRIDOR_ORDER
    }
    abras_path = PACKAGE / "BRECHA_LAS_ABRAS_FINAL.geojson"
    if abras_path.exists():
        abras = gpd.read_file(abras_path).to_crs(METRIC_CRS)
        corridors["QUEBRADA_LAS_ABRAS"] = unary_union(abras.geometry)
    all_cameras = (
        camera_rows("CAMARAS_EXISTENTES_103_FINAL.geojson", "existing")
        + camera_rows("PROPUESTA_MUNICIPAL_50_FINAL.geojson", "municipal")
        + camera_rows("PROPUESTA_POLICIA_30_FINAL.geojson", "police")
    )
    by_group = {
        "existing": [camera for camera in all_cameras if camera["group"] == "existing"],
        "municipal": [camera for camera in all_cameras if camera["group"] == "municipal"],
        "police": [camera for camera in all_cameras if camera["group"] == "police"],
    }
    scenarios = {
        "A": ["existing"],
        "B": ["existing", "municipal"],
        "C": ["existing", "municipal", "police"],
    }
    result = {
        "metadata": {
            "radiusM": RADIUS_M,
            "metricCrs": METRIC_CRS,
            "visualCrs": VISUAL_CRS,
            "sourcePackage": PACKAGE.name,
            "corridors": CORRIDOR_ORDER,
            "scenarioLabels": {
                "A": "EXISTENTES · 103",
                "B": "EXISTENTES + MUNICIPALES · 153",
                "C": "SISTEMA COMPLETO · 183",
            },
        },
        "corridorNames": CORRIDOR_NAMES,
        "scenarios": {},
    }
    for scenario, groups in scenarios.items():
        cameras = [camera for group in groups for camera in by_group[group]]
        scenario_out = {"label": result["metadata"]["scenarioLabels"][scenario], "corridors": {}, "cameras": []}
        for corridor_key in CORRIDOR_ORDER:
            axis = corridors[corridor_key]
            buffer_geometries = [camera["point"].buffer(RADIUS_M, quad_segs=64) for camera in cameras]
            union_buffer = unary_union(buffer_geometries) if buffer_geometries else axis.buffer(0)
            covered = axis.intersection(union_buffer)
            uncovered = axis.difference(union_buffer)
            camera_values = []
            reference_values = []
            for camera in cameras:
                local = camera["point"].buffer(RADIUS_M, quad_segs=64).intersection(axis)
                props = camera["props"]
                camera_id = props.get("ID_CAMARA") or props.get("ID_PROPUESTA") or props.get("ID")
                camera_value = {
                    "id": camera_id,
                    "group": camera["group"],
                    "origin": GROUP_NAMES[camera["group"]],
                    "type": props.get("TIPO") or props.get("SUBTIPO") or "Cámara",
                    "requiresChange": bool(props.get("REQUIERE_CAMBIO")) if camera["group"] == "existing" else False,
                    "lengthM": round(float(local.length), 3),
                    "status": "CONTRIBUYE" if local.length > 0.01 else "REFERENCIA_SIN_INTERSECCION",
                    "lng": float(TO_VISUAL(camera["point"].x, camera["point"].y)[0]),
                    "lat": float(TO_VISUAL(camera["point"].x, camera["point"].y)[1]),
                }
                if local.length > 0.01:
                    camera_values.append(camera_value)
                if props.get("CORREDOR") == corridor_key:
                    reference_values.append(camera_value)
            scenario_out["corridors"][corridor_key] = {
                "name": CORRIDOR_NAMES[corridor_key],
                "totalM": round(float(axis.length), 3),
                "coveredM": round(float(covered.length), 3),
                "uncoveredM": round(float(uncovered.length), 3),
                "coveredPct": round(float(covered.length / axis.length * 100), 6) if axis.length else 0,
                "covered": feature_collection(line_features(covered, corridor_key, "CUBIERTO", f"{corridor_key}-CUB", cameras)),
                "uncovered": feature_collection(line_features(uncovered, corridor_key, "SIN_COBERTURA", f"{corridor_key}-SIN", cameras)),
                "cameras": camera_values,
                "referenceCameras": reference_values,
            }
        for camera in cameras:
            props = camera["props"]
            camera_corridors = []
            for corridor_key, axis in corridors.items():
                length = camera["point"].buffer(RADIUS_M, quad_segs=64).intersection(axis).length
                if length > 0.01:
                    camera_corridors.append({"key": corridor_key, "name": CORRIDOR_NAMES[corridor_key], "lengthM": round(float(length), 3), "status": "CONTRIBUYE"})
            assigned_corridor = camera["props"].get("CORREDOR")
            if assigned_corridor in CORRIDOR_ORDER and not any(item["key"] == assigned_corridor for item in camera_corridors):
                camera_corridors.append({"key": assigned_corridor, "name": CORRIDOR_NAMES[assigned_corridor], "lengthM": 0, "status": "REFERENCIA_SIN_INTERSECCION"})
            if not camera_corridors:
                continue
            scenario_out["cameras"].append({
                "id": props.get("ID_CAMARA") or props.get("ID_PROPUESTA") or props.get("ID"),
                "group": camera["group"],
                "origin": GROUP_NAMES[camera["group"]],
                "type": props.get("TIPO") or props.get("SUBTIPO") or "Cámara",
                "requiresChange": bool(props.get("REQUIERE_CAMBIO")) if camera["group"] == "existing" else False,
                "lng": float(TO_VISUAL(camera["point"].x, camera["point"].y)[0]),
                "lat": float(TO_VISUAL(camera["point"].x, camera["point"].y)[1]),
                "corridors": camera_corridors,
            })
        result["scenarios"][scenario] = scenario_out
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT)
    for scenario, values in result["scenarios"].items():
        print(scenario, [(key, round(v["coveredPct"], 3), round(v["uncoveredM"], 1)) for key, v in values["corridors"].items()])


if __name__ == "__main__":
    main()
