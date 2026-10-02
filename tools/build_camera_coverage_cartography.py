"""Metric replacement-camera geometry for display; no analytical results change."""
import json

from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

from build_remaining_camera_coverage import ROOT, PROJECT, UNPROJECT, PROTECTED, digest, load, read_js


def main():
    protected = {file: digest(file) for file in PROTECTED}
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
    census_source = "riobamba-censo-data/riobamba_manzanas.geojson"
    blocks = [(feature["properties"]["man"], transform(PROJECT, shape(feature["geometry"])))
              for feature in load(census_source)["features"]]
    remaining = read_js("riobamba-camaras-restantes-cobertura-data.js")
    result["censusClips"] = {}
    for universe, dataset in (("municipal", result), ("remaining", remaining)):
        clips = {}
        for radius in (100, 150, 200):
            coverage = transform(PROJECT, shape(dataset["scenarios"][str(radius)]["coverage"]["geometry"]))
            features = []
            for code, block in blocks:
                if not block.intersects(coverage):
                    continue
                covered = block.intersection(coverage)
                if covered.area <= .01:
                    continue
                assert covered.is_valid and covered.difference(block).area < .001
                assert covered.difference(coverage).area < .001
                features.append({"type": "Feature", "properties": {"man": code,
                    "block_area_m2": block.area, "covered_area_m2": covered.area},
                    "geometry": mapping(transform(UNPROJECT, covered))})
            clips[str(radius)] = {"type": "FeatureCollection", "features": features}
            print(json.dumps({"universe": universe, "radius_m": radius, "clipped_blocks": len(features)}), flush=True)
        result["censusClips"][universe] = clips
    result["metadata"].update({"censusSource": census_source, "censusSha256": digest(census_source),
        "clipMethod": "Interseccion de cada manzana con la cobertura disuelta en EPSG:32717; sin recorte por Plataforma",
        "remainingCoverageSha256": digest("riobamba-camaras-restantes-cobertura-data.js")})
    (ROOT / "riobamba-camaras-cobertura-geometrias.js").write_text("window.RIOBAMBA_CAMERA_COVERAGE_GEOMETRIES = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    assert digest(source) == checksum
    assert all(digest(file) == checksum for file, checksum in protected.items())
    print(json.dumps({"cameras": len(cameras), "radii_m": [100, 150, 200], "analytical_values_preserved": True}))


if __name__ == "__main__":
    main()
