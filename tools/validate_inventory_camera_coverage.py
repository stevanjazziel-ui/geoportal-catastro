"""Validate the full inventory independently against metric unions and CPV intersections."""
import json
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union
from build_remaining_camera_coverage import PROJECT, digest, load, read_js


def main():
    data = read_js("riobamba-camaras-inventario-cobertura-data.js")
    meta = data["metadata"]
    inventory = read_js("riobamba-camaras-inventario-data.js")["cameras"]
    located = [camera for camera in inventory if camera["mappable"]]
    assert len(inventory) == len(set(meta["cameraIds"])) == 103
    assert len(located) == len(meta["locatedIds"]) == 99
    assert len(meta["pendingRecords"]) == 4
    assert set(meta["cameraIds"]) == {camera["id"] for camera in inventory}
    assert all(digest(file) == value for file, value in meta["sourceHashes"].items())
    platforms = {feature["properties"]["platform_name"]: transform(PROJECT, shape(feature["geometry"]))
        for feature in load("riobamba-censo-data/riobamba_plataformas.geojson")["features"]}
    urban = unary_union(list(platforms.values()))
    census = load("riobamba-censo-data/riobamba_manzanas_stats.json")["byMan"]
    blocks = [(feature["properties"]["man"], transform(PROJECT, shape(feature["geometry"])))
        for feature in load("riobamba-censo-data/riobamba_manzanas.geojson")["features"]]
    baseline = read_js("riobamba-conflictividad-data.js")["derivedMethodology"]["cameraScenarios"]
    remaining = read_js("riobamba-camaras-restantes-cobertura-data.js")["scenarios"]
    cartography = read_js("riobamba-camaras-cobertura-geometrias.js")
    display = cartography["scenarios"]
    assert digest("riobamba-camaras-inventario-cobertura-data.js") == cartography["metadata"]["inventoryCoverageSha256"]
    points = [Point(PROJECT(camera["lng"], camera["lat"])) for camera in located]
    results, previous = [], None
    for radius in (100, 150, 200):
        scenario = data["scenarios"][str(radius)]
        expected = unary_union([point.buffer(radius, quad_segs=64) for point in points])
        actual = transform(PROJECT, shape(scenario["coverage"]["geometry"]))
        outside = transform(PROJECT, shape(scenario["uncovered"]["geometry"]))
        assert actual.is_valid and outside.is_valid
        assert actual.symmetric_difference(expected).area < .02
        assert outside.symmetric_difference(urban.difference(expected)).area < .02
        assert abs(scenario["totalCoveredAreaKm2"] - urban.intersection(expected).area / 1e6) < 1e-9
        old_union = transform(PROJECT, shape(display[str(radius)]["coverage"]["geometry"]))
        remaining_union = transform(PROJECT, shape(remaining[str(radius)]["coverage"]["geometry"]))
        assert actual.symmetric_difference(unary_union([old_union, remaining_union])).area < .02
        assert actual.area < old_union.area + remaining_union.area, "Do not sum overlapping universes"
        populations = {name: 0. for name in platforms}
        features = cartography["censusClips"]["inventory"][str(radius)]["features"]
        clips = {feature["properties"]["man"]: feature for feature in features}
        assert len(clips) == len(features)
        for code, block in blocks:
            pop = float(census.get(code, {}).get("population_total") or 0)
            covered = block.intersection(expected)
            if covered.area > .01:
                clipped = transform(PROJECT, shape(clips[code]["geometry"]))
                assert clipped.is_valid and clipped.symmetric_difference(covered).area < .02
                assert clipped.difference(block).area < .001 and clipped.difference(expected).area < .001
            else:
                assert code not in clips
            assert abs(scenario["byMan"][code] - covered.area / block.area) < 1e-9
            for name, platform in platforms.items():
                if block.intersects(platform):
                    populations[name] += pop * covered.intersection(platform).area / block.area
        for name, row in scenario["byPlatformName"].items():
            assert row["coveredPopulation"] == min(row["population"], round(populations[name]))
            assert row["population"] == row["coveredPopulation"] + row["uncoveredPopulation"]
            assert row["coveredPopulation"] >= baseline[str(radius)]["byPlatformName"][name]["coveredPopulation"]
            assert row["cameras"] == sum(platforms[name].covers(point) for point in points)
            assert abs(row["coveredAreaKm2"] - platforms[name].intersection(expected).area / 1e6) < 1e-9
        if previous is not None:
            assert previous.difference(actual).area < .02
        previous = actual
        results.append({"radius": radius, "urbanCoveredAreaKm2": scenario["totalCoveredAreaKm2"],
            "populationCovered": sum(row["coveredPopulation"] for row in scenario["byPlatformName"].values()),
            "populationOutside": sum(row["uncoveredPopulation"] for row in scenario["byPlatformName"].values())})
    print(json.dumps({"inventory": 103, "located": 99, "pending": 4, "baselineUnchanged": True,
        "dissolvedUnionVerified": True, "populationIntersectionsVerified": True,
        "clippedCensusVerified": True, "scenarios": results}))


if __name__ == "__main__":
    main()
