"""Independent checks against the active GeoPackage, including disjoint ID sets."""
import json
from pathlib import Path
import unittest

import numpy as np
import pyogrio
from shapely import intersection, area
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

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
        canton = unary_union(pyogrio.read_dataframe(package, layer="LIMITE_CANTONAL").geometry)
        self.assertEqual(data["schemaVersion"], 3)
        blocks = pyogrio.read_dataframe(package, layer="MANZANAS_COBERTURA")
        base = json.loads((release / data["blocksFile"]).read_text(encoding="utf-8"))
        self.assertEqual(len(base["features"]), len(blocks))
        self.assertEqual(len({f["properties"]["ID_MANZANA"] for f in base["features"]}), len(blocks))
        all_geometries = blocks.geometry.to_numpy()
        all_areas = area(all_geometries)
        block_union = unary_union(blocks.geometry)
        project = Transformer.from_crs(4326, 32717, always_xy=True).transform
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
                canton_area = masks[key].intersection(canton).area / 1e6
                exterior_area = masks[key].difference(canton).area / 1e6
                self.assertAlmostEqual(row["coveredCantonAreaKm2"], canton_area, places=8)
                self.assertAlmostEqual(row["outsideCantonAreaKm2"], exterior_area, places=8)
                self.assertAlmostEqual(row["dissolvedAreaKm2"], canton_area + exterior_area, places=8)
                self.assertAlmostEqual(row["coveredCantonAreaPct"], 100 * canton_area / row["cantonAreaKm2"], places=8)
                self.assertAlmostEqual(row["coveredPlatformAreaKm2"], masks[key].intersection(urban).area / 1e6, places=8)
                actual = float(np.sum(populations * area(intersection(geometries, masks[key])) / block_areas))
                self.assertAlmostEqual(row["coveredPopulation"], actual, places=5)
                areas = area(intersection(all_geometries, masks[key]))
                empty = areas <= .01
                full = (~empty) & ((all_areas - areas) <= np.maximum(.01, all_areas * 1e-6))
                stats = row["blockStats"]
                self.assertEqual(stats["total"], len(blocks))
                self.assertEqual(stats["full"], int(full.sum()))
                self.assertEqual(stats["uncovered"], int(empty.sum()))
                self.assertEqual(stats["partial"], len(blocks) - int(empty.sum()) - int(full.sum()))
                self.assertEqual(stats["covered"], stats["full"] + stats["partial"])
                self.assertAlmostEqual(stats["coveredAreaKm2"], block_union.intersection(masks[key]).area / 1e6, places=8)
                self.assertAlmostEqual(stats["coveredCantonAreaKm2"], block_union.intersection(masks[key]).intersection(canton).area / 1e6, places=8)
                clips = json.loads((release / row["blockClipsFile"]).read_text(encoding="utf-8"))
                self.assertEqual(len(clips["features"]), stats["covered"])
                self.assertEqual(len({f["properties"]["ID_MANZANA"] for f in clips["features"]}), stats["covered"])
                self.assertEqual(sum(f["properties"]["ESTADO"] == "full" for f in clips["features"]), stats["full"])
                sample = next(f for f in clips["features"] if 1 < f["properties"]["COBERTURA_PCT"] < 10)
                drawn = transform(project, shape(sample["geometry"]))
                self.assertLess(drawn.area, sample["properties"]["AREA_M2"] * .2)
                self.assertLess(drawn.difference(masks[key].buffer(.51)).area, .01)
                for f in clips["features"]:
                    props = f["properties"]
                    self.assertGreater(props["AREA_CUBIERTA_M2"], .01)
                    self.assertLessEqual(props["AREA_CUBIERTA_M2"], props["AREA_M2"])
                    self.assertAlmostEqual(props["COBERTURA_PCT"], 100 * props["AREA_CUBIERTA_M2"] / props["AREA_M2"])
                    if props["POBLACION"] is None:
                        self.assertIsNone(props["POBLACION_CUBIERTA"])
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
