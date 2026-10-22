"""Metric coverage for the current 73 / intervention 110 / combined 183 groups."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import pyogrio
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform, unary_union

from build_camera_population_comparison import population_comparison


def build_coverage(existing, municipal, police, blocks, platforms, output=None, *, canton):
    urban = unary_union([g for g, _ in platforms])
    groups = {
        "current": [(g, p) for g, p in existing if not p["REQUIERE_CAMBIO"]],
        "interventions": [(g, p) for g, p in existing if p["REQUIERE_CAMBIO"]] + municipal + police,
        "combined": existing + municipal + police,
    }
    if [len(rows) for rows in groups.values()] != [73, 110, 183]:
        raise ValueError("Camera groups must be 73, 110, 183")
    unproject = Transformer.from_crs(32717, 4326, always_xy=True).transform
    block_union = unary_union([g for g, _ in blocks])
    block_ids = [str(p.get("ID_MANZANA") or p["man"]) for _, p in blocks]
    if len(set(block_ids)) != len(blocks) or any(g.is_empty or g.area <= 0 for g, _ in blocks):
        raise ValueError("Census blocks need unique IDs and positive areas")

    def population_value(p):
        value = p.get("POBLACION")
        return value if value is not None and math.isfinite(value) else None

    def feature(geometry, properties):
        return {"type": "Feature", "properties": properties,
                "geometry": mapping(transform(unproject, geometry.simplify(.5, preserve_topology=True)))}

    def write_features(name, features):
        if output is not None:
            (Path(output) / name).write_text(json.dumps({"type": "FeatureCollection", "features": features},
                ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")

    write_features("MANZANAS_BASE_COBERTURA.geojson", [feature(g, {"ID_MANZANA": code,
        "AREA_M2": g.area, "POBLACION": population_value(p)}) for (g, p), code in zip(blocks, block_ids)])
    result = {"schemaVersion": 3, "crsMetric": "EPSG:32717", "bufferQuadSegments": 64,
              "mapSimplificationM": .5, "blockAreaToleranceM2": .01, "fullBlockFractionTolerance": 1e-6,
              "cantonBoundary": feature(canton, {"scope": "Limite cantonal de Riobamba"}),
              "blocksFile": "MANZANAS_BASE_COBERTURA.geojson", "scenarios": {}}
    for radius in (100, 150, 200):
        comparison = population_comparison(existing, municipal, police, blocks, urban, radius, True)
        scenario = {"population": comparison, "groups": {}}
        for (key, cameras), population in zip(groups.items(), comparison["scenarios"]):
            mask = unary_union([g.buffer(radius, quad_segs=64) for g, _ in cameras])
            counts = {"full": 0, "partial": 0, "uncovered": 0}
            clipped_features = []
            for (geom, props), code in zip(blocks, block_ids):
                covered = geom.intersection(mask)
                covered_area = min(geom.area, max(0., covered.area))
                status = "uncovered" if covered_area <= .01 else "full" if geom.area - covered_area <= max(.01, geom.area * 1e-6) else "partial"
                counts[status] += 1
                if status == "uncovered":
                    continue
                pop = props.get("POBLACION")
                pop = pop if pop is not None and math.isfinite(pop) else None
                clipped_features.append(feature(covered, {"ID_MANZANA": code, "ESTADO": status,
                    "AREA_M2": geom.area, "AREA_CUBIERTA_M2": covered_area,
                    "COBERTURA_PCT": 100 * covered_area / geom.area,
                    "POBLACION": pop, "POBLACION_CUBIERTA": pop * covered_area / geom.area if pop is not None else None}))
            clips_file = f"MANZANAS_CUBIERTAS_{key}_{radius}M.geojson"
            write_features(clips_file, clipped_features)
            scenario["groups"][key] = {**population, "platformAreaKm2": urban.area / 1e6,
                "cantonAreaKm2": canton.area / 1e6,
                "coveredCantonAreaKm2": mask.intersection(canton).area / 1e6,
                "coveredCantonAreaPct": 100 * mask.intersection(canton).area / canton.area,
                "outsideCantonAreaKm2": mask.difference(canton).area / 1e6,
                "blockStats": {**counts, "total": len(blocks), "covered": counts["full"] + counts["partial"],
                    "coveredAreaKm2": block_union.intersection(mask).area / 1e6,
                    "coveredCantonAreaKm2": block_union.intersection(mask).intersection(canton).area / 1e6,
                    "totalAreaKm2": block_union.area / 1e6},
                "blockClipsFile": clips_file,
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
        read("PROPUESTA_POLICIA_30_FINAL"), read("MANZANAS_COBERTURA"), read("PLATAFORMAS_TERRITORIALES"), args.release,
        canton=unary_union([g for g, _ in read("LIMITE_CANTONAL")]))
    result["sourcePackageSha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
    (args.release / "COBERTURA_73_110_183.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")), encoding="utf-8")
    print(json.dumps({r: {k: {field: row[field] for field in ("cameraCount", "dissolvedAreaKm2", "coveredPlatformAreaKm2", "blockStats")}
        for k, row in s["groups"].items()} for r, s in result["scenarios"].items()}, indent=2))


if __name__ == "__main__":
    main()
