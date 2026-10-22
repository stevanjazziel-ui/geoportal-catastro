"""Metric coverage for the current 73 / intervention 110 / combined 183 groups."""
import argparse
import hashlib
import json
from pathlib import Path

import pyogrio
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform, unary_union

from build_camera_population_comparison import population_comparison


def build_coverage(existing, municipal, police, blocks, platforms):
    urban = unary_union([g for g, _ in platforms])
    groups = {
        "current": [(g, p) for g, p in existing if not p["REQUIERE_CAMBIO"]],
        "interventions": [(g, p) for g, p in existing if p["REQUIERE_CAMBIO"]] + municipal + police,
        "combined": existing + municipal + police,
    }
    if [len(rows) for rows in groups.values()] != [73, 110, 183]:
        raise ValueError("Camera groups must be 73, 110, 183")
    unproject = Transformer.from_crs(32717, 4326, always_xy=True).transform
    result = {"schemaVersion": 1, "crsMetric": "EPSG:32717", "bufferQuadSegments": 64,
              "mapSimplificationM": .5, "scenarios": {}}
    for radius in (100, 150, 200):
        comparison = population_comparison(existing, municipal, police, blocks, urban, radius, True)
        scenario = {"population": comparison, "groups": {}}
        for (key, cameras), population in zip(groups.items(), comparison["scenarios"]):
            mask = unary_union([g.buffer(radius, quad_segs=64) for g, _ in cameras])
            scenario["groups"][key] = {**population, "platformAreaKm2": urban.area / 1e6,
                "coveredPlatformAreaKm2": mask.intersection(urban).area / 1e6,
                "coveredPlatformAreaPct": 100 * mask.intersection(urban).area / urban.area,
                "dissolvedAreaKm2": mask.area / 1e6,
                "coverage": {"type": "Feature", "properties": {"group": key, "radiusM": radius},
                    "geometry": mapping(transform(unproject, mask.simplify(.5, preserve_topology=True)))},
                "platforms": [{"name": p["platform_name"], "areaKm2": g.area / 1e6,
                    "coveredAreaKm2": g.intersection(mask).area / 1e6,
                    "coveredPct": 100 * g.intersection(mask).area / g.area,
                    "cameraCount": sum(g.covers(point) for point, _ in cameras)} for g, p in platforms]}
        result["scenarios"][str(radius)] = scenario
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    package = args.release / "ESCENARIO_FINAL_183.gpkg"

    def read(name):
        frame = pyogrio.read_dataframe(package, layer=name)
        if frame.crs.to_epsg() != 32717:
            raise ValueError("Metric CRS required")
        return [(row.geometry, row.drop("geometry").to_dict()) for _, row in frame.iterrows()]

    result = build_coverage(read("CAMARAS_EXISTENTES_103_FINAL"), read("PROPUESTA_MUNICIPAL_50_FINAL"),
        read("PROPUESTA_POLICIA_30_FINAL"), read("MANZANAS_COBERTURA"), read("PLATAFORMAS_TERRITORIALES"))
    result["sourcePackageSha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
    (args.release / "COBERTURA_73_110_183.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")), encoding="utf-8")
    print(json.dumps({r: {k: {field: row[field] for field in ("cameraCount", "coveredPopulation", "censusUrbanCoveredPopulation", "coveredPlatformAreaKm2")}
        for k, row in s["groups"].items()} for r, s in result["scenarios"].items()}, indent=2))


if __name__ == "__main__":
    main()
