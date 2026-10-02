"""Metric replacement-camera geometry for display; no analytical results change."""
import json

from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

from build_remaining_camera_coverage import ROOT, PROJECT, UNPROJECT, digest, read_js


def main():
    source = "riobamba-camaras-data.js"
    checksum = digest(source)
    cameras = read_js(source)["cameras"]
    assert len(cameras) == 31 and all(camera["requiresChange"] for camera in cameras)
    methodology = read_js("riobamba-conflictividad-data.js")["derivedMethodology"]
    canton = read_js("riobamba-cantonal-data.js")
    urban = transform(PROJECT, shape(canton["urban"]["geometry"]))
    points = [Point(PROJECT(camera["lng"], camera["lat"])) for camera in cameras]
    scenarios = {}
    for radius in (100, 150, 200):
        coverage = unary_union([point.buffer(radius, quad_segs=64) for point in points])
        assert coverage.is_valid
        assert abs(coverage.intersection(urban).area / 1e6 - methodology["cameraScenarios"][str(radius)]["totalCoveredAreaKm2"]) < 1e-8
        scenarios[str(radius)] = {"coverage": {"type": "Feature", "properties": {"universe": "CAMARAS_PARA_CAMBIO", "radius_m": radius, "crs_calculation": "EPSG:32717", "cameras": len(cameras)}, "geometry": mapping(transform(UNPROJECT, coverage))}}
    result = {"metadata": {"source": source, "sha256": checksum, "crs": "EPSG:32717", "cameraIds": [camera["id"] for camera in cameras], "purpose": "Geometria visual disuelta; manzanas sin relleno completo; indicadores originales intactos"}, "scenarios": scenarios}
    (ROOT / "riobamba-camaras-cobertura-geometrias.js").write_text("window.RIOBAMBA_CAMERA_COVERAGE_GEOMETRIES = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    assert digest(source) == checksum
    print(json.dumps({"cameras": len(cameras), "radii_m": [100, 150, 200], "analytical_values_preserved": True}))


if __name__ == "__main__":
    main()
