"""Compare unchanged cameras with the full proposal using the existing areal method."""
import argparse
import json
import math
from pathlib import Path

import pyogrio
from shapely.ops import unary_union


def is_census_urban(properties):
    code = str(properties.get("man") or properties.get("ID_MANZANA") or "")
    return len(code) == 15 and code.startswith("060150") and code[6:9].isdigit() and 1 <= int(code[6:9]) <= 899


def population_comparison(existing, municipal, police, blocks, urban, radius=200, include_interventions=False):
    current = [g for g, p in existing if not p["REQUIERE_CAMBIO"]]
    all_cameras = [g for g, _ in existing + municipal + police]
    if len(current) != 73 or len(all_cameras) != 183:
        raise ValueError("Expected 73 unchanged cameras and 183 total cameras")
    valid = [(g, p["POBLACION"]) for g, p in blocks
             if p.get("POBLACION") is not None and math.isfinite(p["POBLACION"])]
    total = sum(pop for _, pop in valid)
    census_urban = [(g, p["POBLACION"]) for g, p in blocks if is_census_urban(p)
                    and p.get("POBLACION") is not None and math.isfinite(p["POBLACION"])]
    mapped_urban = sum(pop for _, pop in census_urban)
    platform_population = sum(pop * geom.intersection(urban).area / geom.area for geom, pop in valid)
    rows = []
    groups = [(73, current), (183, all_cameras)]
    if include_interventions:
        groups.insert(1, (110, [g for g, p in existing if p["REQUIERE_CAMBIO"]] + [g for g, _ in municipal + police]))
    for count, cameras in groups:
        mask = unary_union([g.buffer(radius, quad_segs=64) for g in cameras])
        inside_mask = mask.intersection(urban)
        covered = sum(pop * geom.intersection(mask).area / geom.area for geom, pop in valid)
        inside = sum(pop * geom.intersection(inside_mask).area / geom.area for geom, pop in valid)
        urban_covered = sum(pop * geom.intersection(mask).area / geom.area for geom, pop in census_urban)
        rows.append({"cameraCount": count, "coveredPopulation": covered,
                     "censusUrbanCoveredPopulation": urban_covered,
                     "censusUrbanCoveredPct": 100 * urban_covered / 177213,
                     "insidePlatformPopulation": inside, "outsidePlatformPopulation": covered - inside,
                     "missingPopulationBlocksCovered": sum(g.intersection(mask).area > 0 for g, p in blocks
                         if p.get("POBLACION") is None or not math.isfinite(p["POBLACION"])),
                     "coveredPct": 100 * covered / total if total else None})
    return {"radiusM": radius, "crs": "EPSG:32717", "scope": "Todas las manzanas disponibles, dentro y fuera de plataformas",
            "officialUrbanReferencePopulation": 177213, "insidePlatformAnalyzedPopulation": platform_population,
            "mappedCensusUrbanPopulation": mapped_urban, "urbanPopulationPendingReconciliation": 177213 - mapped_urban,
            "urbanRule": "060150, zonas 001-899; periferia 901-999 y parroquias 51+ separadas",
            "method": "CPV2022, distribucion uniforme por area de manzana; buffers disueltos",
            "analyzedPopulation": total,
            "blocksWithoutPopulation": len(blocks) - len(valid), "scenarios": rows,
            "additionalPopulation": rows[-1]["coveredPopulation"] - rows[0]["coveredPopulation"],
            "percentagePointGain": rows[-1]["coveredPct"] - rows[0]["coveredPct"] if total else None}


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
    if abs(full["POBLACION_CUBIERTA"] - comparison["scenarios"][1]["insidePlatformPopulation"]) > .1:
        raise ValueError("Inside-platform subtotal differs from the published calculation")
    results["populationComparison"] = comparison
    path.write_text(json.dumps(results, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
