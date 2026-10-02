"""Independent checks of the remaining-camera metric union and protected inputs."""
import json

from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

from build_remaining_camera_coverage import ROOT, PROJECT, digest, load, read_js


def main():
    data = read_js("riobamba-camaras-restantes-cobertura-data.js")
    meta = data["metadata"]
    study_ids = {camera["id"] for camera in read_js("riobamba-camaras-data.js")["cameras"]}
    remaining = [camera for camera in read_js("riobamba-camaras-inventario-data.js")["cameras"] if camera["id"] not in study_ids]
    located = [camera for camera in remaining if camera["mappable"]]
    assert len(remaining) == meta["totalRecords"] == 72
    assert len(located) == meta["locatedRecords"] == 68
    assert not study_ids.intersection(meta["cameraIds"])
    assert {camera["id"] for camera in remaining} == set(meta["cameraIds"])
    assert {camera["id"] for camera in remaining if not camera["mappable"]} == {camera["id"] for camera in meta["pendingRecords"]}
    assert all(digest(file) == checksum for file, checksum in meta["sourceHashes"].items())
    platforms = {feature["properties"]["platform_name"]: transform(PROJECT, shape(feature["geometry"]))
                 for feature in load("riobamba-censo-data/riobamba_plataformas.geojson")["features"]}
    urban = unary_union(list(platforms.values()))
    territory = read_js("riobamba-cantonal-data.js")
    canton = transform(PROJECT, shape(territory["canton"]["geometry"]))
    rural = canton.difference(urban)
    points = [Point(PROJECT(camera["lng"], camera["lat"])) for camera in located]
    display = read_js("riobamba-camaras-cobertura-geometrias.js")
    assert digest(display["metadata"]["source"]) == display["metadata"]["sha256"]
    assert digest(display["metadata"]["censusSource"]) == display["metadata"]["censusSha256"]
    assert digest("riobamba-camaras-restantes-cobertura-data.js") == display["metadata"]["remainingCoverageSha256"]
    blocks = {feature["properties"]["man"]: transform(PROJECT, shape(feature["geometry"]))
              for feature in load(display["metadata"]["censusSource"])["features"]}
    study_points = [Point(PROJECT(camera["lng"], camera["lat"])) for camera in read_js("riobamba-camaras-data.js")["cameras"]]
    previous = None
    checked = []
    for radius in (100, 150, 200):
        study_expected = unary_union([point.buffer(radius, quad_segs=64) for point in study_points])
        study_display = transform(PROJECT, shape(display["scenarios"][str(radius)]["coverage"]["geometry"]))
        assert study_display.is_valid and study_display.symmetric_difference(study_expected).area < .02
        scenario = data["scenarios"][str(radius)]
        expected = unary_union([point.buffer(radius, quad_segs=64) for point in points])
        actual = transform(PROJECT, shape(scenario["coverage"]["geometry"]))
        assert actual.is_valid
        assert actual.symmetric_difference(expected).area < .02, "Exported geometry differs from metric buffers"
        for universe, coverage in (("municipal", study_expected), ("remaining", expected)):
            features = display["censusClips"][universe][str(radius)]["features"]
            clips = {feature["properties"]["man"]: feature for feature in features}
            assert len(clips) == len(features), "Duplicate census block geometry"
            for code, block in blocks.items():
                intersection = block.intersection(coverage)
                if intersection.area <= .01:
                    assert code not in clips, "Painted a block outside coverage"
                    continue
                feature = clips[code]
                clipped = transform(PROJECT, shape(feature["geometry"]))
                assert clipped.is_valid and clipped.symmetric_difference(intersection).area < .02
                assert clipped.difference(block).area < .001
                assert clipped.difference(coverage).area < .001, "Painted census area outside camera radius"
                assert abs(feature["properties"]["covered_area_m2"] - intersection.area) < .02
                if intersection.area < block.area - .02:
                    assert clipped.area < block.area, "Filled an entire partially covered census block"
        assert all(actual.distance(point) < .001 for point in points)
        assert all(expected.distance(point) == 0 for point in points)
        assert expected.area < len(points) * 3.141593 * radius**2, "Dissolve did not eliminate overlaps"
        for name, geom in [("cantonal", canton), ("rural", rural)]:
            row = scenario[name]
            assert abs(row["coveredAreaKm2"] - geom.intersection(expected).area / 1e6) < 1e-9
            assert row["cameras"] == sum(geom.covers(point) for point in points)
            assert row["population"] is None and row["coveredPopulation"] is None
        assert abs(scenario["totalCoveredAreaKm2"] - urban.intersection(expected).area / 1e6) < 1e-9
        assert len(scenario["byPlatformName"]) == 18
        for name, row in scenario["byPlatformName"].items():
            assert row["coveredPopulation"] + row["uncoveredPopulation"] == row["population"]
            assert abs(row["coveredAreaKm2"] - platforms[name].intersection(expected).area / 1e6) < 1e-9
        if previous is not None:
            assert previous.difference(expected).area < .001
        previous = expected
        checked.append({"radius_m": radius, "located": len(points), "full_area_km2": actual.area / 1e6,
                        "urban_area_km2": scenario["totalCoveredAreaKm2"],
                        "urban_covered_population": sum(row["coveredPopulation"] for row in scenario["byPlatformName"].values())})
    print(json.dumps({"protected_unchanged": True, "remaining": 72, "located": 68, "pending": 4,
                      "metric_union_validated": True, "replacement_display_validated": [100, 150, 200],
                      "clipped_census_blocks_validated": ["municipal", "remaining"], "scenarios": checked}))


if __name__ == "__main__":
    main()
