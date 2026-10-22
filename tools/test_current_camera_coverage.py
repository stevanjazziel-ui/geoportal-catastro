"""Independent checks against the active GeoPackage, including disjoint ID sets."""
import json
from pathlib import Path
import unittest

import numpy as np
import pyogrio
from shapely import intersection, area
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


class CurrentCoverageTest(unittest.TestCase):
    def test_active_package_groups_radii_and_exact_totals(self):
        release = ROOT / json.loads((ROOT / "sig-bridge-active.json").read_text())["root"]
        data = json.loads((release / "COBERTURA_73_110_183.json").read_text(encoding="utf-8"))
        package = release / "ESCENARIO_FINAL_183.gpkg"
        existing = pyogrio.read_dataframe(package, layer="CAMARAS_EXISTENTES_103_FINAL")
        municipal = pyogrio.read_dataframe(package, layer="PROPUESTA_MUNICIPAL_50_FINAL")
        police = pyogrio.read_dataframe(package, layer="PROPUESTA_POLICIA_30_FINAL")
        ids = set(existing[~existing.REQUIERE_CAMBIO].ID_CAMARA)
        interventions = set(existing[existing.REQUIERE_CAMBIO].ID_CAMARA) | set(municipal.ID_PROPUESTA) | set(police.ID_POLICIA)
        self.assertEqual((len(ids), len(interventions), len(ids | interventions)), (73, 110, 183))
        self.assertFalse(ids & interventions)
        groups = {"current": list(existing[~existing.REQUIERE_CAMBIO].geometry),
                  "interventions": list(existing[existing.REQUIERE_CAMBIO].geometry) + list(municipal.geometry) + list(police.geometry)}
        groups["combined"] = groups["current"] + groups["interventions"]
        urban = unary_union(pyogrio.read_dataframe(package, layer="PLATAFORMAS_TERRITORIALES").geometry)
        blocks = pyogrio.read_dataframe(package, layer="MANZANAS_COBERTURA")
        valid = blocks[blocks.POBLACION.notna()]
        geometries = valid.geometry.to_numpy()
        populations = valid.POBLACION.to_numpy()
        block_areas = area(geometries)
        previous = {key: 0 for key in groups}
        for radius in (100, 150, 200):
            masks = {}
            for key, points in groups.items():
                masks[key] = unary_union([p.buffer(radius, quad_segs=64) for p in points])
                row = data["scenarios"][str(radius)]["groups"][key]
                self.assertEqual(row["cameraCount"], len(points))
                self.assertAlmostEqual(row["coveredPlatformAreaKm2"], masks[key].intersection(urban).area / 1e6, places=8)
                actual = float(np.sum(populations * area(intersection(geometries, masks[key])) / block_areas))
                self.assertAlmostEqual(row["coveredPopulation"], actual, places=5)
                self.assertGreaterEqual(actual, previous[key])
                previous[key] = actual
            self.assertLess(masks["combined"].area, masks["current"].area + masks["interventions"].area)
        results = json.loads((release / "RESULTADOS.json").read_text(encoding="utf-8"))
        comparison = results["populationComparison"]
        latest = data["scenarios"]["200"]["groups"]
        for index, key in ((0, "current"), (1, "combined")):
            self.assertAlmostEqual(latest[key]["coveredPopulation"], comparison["scenarios"][index]["coveredPopulation"])
            self.assertAlmostEqual(latest[key]["censusUrbanCoveredPopulation"], comparison["scenarios"][index]["censusUrbanCoveredPopulation"])


if __name__ == "__main__":
    unittest.main()
