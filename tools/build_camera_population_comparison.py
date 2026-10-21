"""Compare unchanged cameras with the full proposal using the existing areal method."""
import argparse
import json
import math
from pathlib import Path

import pyogrio
from shapely.ops import unary_union


def population_comparison(existing, municipal, police, blocks, urban):
    current = [g for g, p in existing if not p["REQUIERE_CAMBIO"]]
    all_cameras = [g for g, _ in existing + municipal + police]
    if len(current) != 73 or len(all_cameras) != 183:
        raise ValueError("Expected 73 unchanged cameras and 183 total cameras")
    urban_blocks = [(g, p) for g, p in blocks if g.intersection(urban).area > 0]
    valid = [(g, p["POBLACION"]) for g, p in urban_blocks
             if p.get("POBLACION") is not None and math.isfinite(p["POBLACION"])]
    total = sum(pop * geom.intersection(urban).area / geom.area for geom, pop in valid)
    rows = []
    for count, cameras in ((73, current), (183, all_cameras)):
        mask = unary_union([g.buffer(200, quad_segs=64) for g in cameras]).intersection(urban)
        covered = sum(pop * geom.intersection(mask).area / geom.area for geom, pop in valid)
        rows.append({"cameraCount": count, "coveredPopulation": covered,
                     "coveredPct": 100 * covered / total if total else None})
    return {"radiusM": 200, "crs": "EPSG:32717", "scope": "18 plataformas",
            "method": "CPV2022, distribucion uniforme por area de manzana; buffers disueltos",
            "analyzedPopulation": total,
            "blocksWithoutPopulation": len(urban_blocks) - len(valid), "scenarios": rows,
            "additionalPopulation": rows[1]["coveredPopulation"] - rows[0]["coveredPopulation"],
            "percentagePointGain": rows[1]["coveredPct"] - rows[0]["coveredPct"] if total else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    package = args.release / "ESCENARIO_FINAL_183.gpkg"

    def read(name):
        frame = pyogrio.read_dataframe(package, layer=name)
        if frame.crs.to_epsg() != 32717:
            raise ValueError("Metric calculations require EPSG:32717")
        return [(row.geometry, row.drop("geometry").to_dict()) for _, row in frame.iterrows()]

    comparison = population_comparison(read("CAMARAS_EXISTENTES_103_FINAL"),
        read("PROPUESTA_MUNICIPAL_50_FINAL"), read("PROPUESTA_POLICIA_30_FINAL"),
        read("MANZANAS_COBERTURA"), unary_union([g for g, _ in read("PLATAFORMAS_TERRITORIALES")]))
    path = args.release / "RESULTADOS.json"
    results = json.loads(path.read_text(encoding="utf-8"))
    full = next(row for row in results["population"] if row["ESCENARIO"] == "C")
    if abs(full["POBLACION_CUBIERTA"] - comparison["scenarios"][1]["coveredPopulation"]) > .1:
        raise ValueError("183-camera comparison differs from the published calculation")
    results["populationComparison"] = comparison
    path.write_text(json.dumps(results, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
