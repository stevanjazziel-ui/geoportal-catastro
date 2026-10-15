"""Verify the applied police revision against its immutable GIS sources."""
import csv
import hashlib
import json
import unittest
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
from shapely import covers, force_2d
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/seguridad-riobamba"
OLD = BASE / "REUBICACION_POL24_20261007_B"
NEW = BASE / "POLICIA_KDE_INTERSECCIONES_20261015"
REVIEW = BASE / "propuesta-policia-kde-intersecciones-20261014"
CATEGORIES = ("DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA")


def read(folder, layer):
    return pyogrio.read_dataframe(folder / "ESCENARIO_FINAL_183.gpkg", layer=layer)


def load(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8"))


class AppliedPoliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior = load(OLD, "RESULTADOS.json")
        cls.results = load(NEW, "RESULTADOS.json")
        cls.police = read(NEW, "PROPUESTA_POLICIA_30_FINAL")
        cls.mask = read(NEW, "COBERTURA_C").geometry.iloc[0]

    def test_protected_files_and_vectors(self):
        for name, digest in self.results["sourceHashes"].items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), digest, name)
        for name in ("CAMARAS_EXISTENTES_103_FINAL", "PROPUESTA_MUNICIPAL_50_FINAL", "PLATAFORMAS_TERRITORIALES", "CORREDORES"):
            old, new = read(OLD, name), read(NEW, name)
            self.assertEqual(old.crs.to_epsg(), 32717)
            self.assertEqual(new.crs.to_epsg(), 32717)
            self.assertEqual([force_2d(g).wkb for g in old.geometry], [g.wkb for g in new.geometry], name)
            pd.testing.assert_frame_equal(old.drop(columns="geometry"), new.drop(columns="geometry"), check_dtype=False)
            self.assertEqual((OLD / (name+".geojson")).read_bytes(), (NEW / (name+".geojson")).read_bytes())

    def test_positions_match_review_and_inventory(self):
        with (REVIEW / "MOVIMIENTOS_POLICIA_30.csv").open(encoding="utf-8-sig") as stream:
            reviewed = {row["ID_POLICIA"]: row for row in csv.DictReader(stream)}
        self.assertEqual(len(self.police), 30)
        self.assertEqual(self.police.geometry.nunique(), 30)
        self.assertEqual(len(read(NEW, "ESCENARIO_FINAL_183")), 183)
        for _, row in self.police.iterrows():
            source = reviewed[row.ID_POLICIA]
            self.assertAlmostEqual(row.geometry.x, float(source["X_DESPUES"]), places=6)
            self.assertAlmostEqual(row.geometry.y, float(source["Y_DESPUES"]), places=6)
            self.assertLessEqual(row.DISTANCIA_NODO_M, 1e-6)
            self.assertGreaterEqual(row.GRADO_NODO, 3)
            self.assertFalse(row.COBERTURA_VISUAL_CERTIFICADA)

    def test_buffers_and_exclusive_metrics(self):
        baseline = read(NEW, "COBERTURA_B").geometry.iloc[0]
        disks = [g.buffer(200, quad_segs=64) for g in self.police.geometry]
        expected = unary_union([baseline, *disks])
        self.assertLess(expected.symmetric_difference(self.mask).area, .01)
        for index, (_, row) in enumerate(self.police.iterrows()):
            others = unary_union([baseline, *[d for i, d in enumerate(disks) if i != index]])
            overlap = 100*disks[index].intersection(others).area/disks[index].area
            self.assertAlmostEqual(row.SOLAPE_PREVIO_PCT, overlap, places=6)

    def test_gi_statistics_and_geometries_unchanged(self):
        for scope in ("URBANO", "RURAL"):
            for category in CATEGORIES:
                name = f"GI_{scope}_{category}"
                old, new = read(OLD, name), read(NEW, name)
                self.assertEqual([g.wkb for g in old.geometry], [g.wkb for g in new.geometry], name)
                fields = [c for c in old.columns if c not in ("geometry", "COB_C_PCT", "ESTADO_C")]
                pd.testing.assert_frame_equal(old[fields], new[fields], check_dtype=False)

    def test_scenarios_and_incidents(self):
        for key in ("territorial", "population", "incidents", "hotspots", "corridors"):
            self.assertEqual([r for r in self.prior[key] if r["ESCENARIO"] != "C"],
                             [r for r in self.results[key] if r["ESCENARIO"] != "C"])
        old, new = read(OLD, "INCIDENTES_CLASIFICADOS"), read(NEW, "INCIDENTES_CLASIFICADOS")
        self.assertEqual([g.wkb for g in old.geometry], [g.wkb for g in new.geometry])
        self.assertTrue(np.array_equal(covers(self.mask, np.asarray(new.geometry)), np.asarray(new.CUB_C)))
        fields = [c for c in old.columns if c not in ("geometry", "CUB_C")]
        pd.testing.assert_frame_equal(old[fields], new[fields], check_dtype=False)

    def test_corridor_view_and_downloads(self):
        view = load(NEW, "CORRIDOR_COVERAGE_200M.json")
        for code in ("A", "B", "C"):
            for key, value in view["scenarios"][code]["corridors"].items():
                metric = next(r for r in self.results["corridors"] if r["ESCENARIO"] == code and r["CORREDOR"] == key)
                self.assertAlmostEqual(value["coveredM"], metric["CUBIERTO_M"], places=4)
                self.assertTrue(all(r["id"] for r in value["cameras"]))
        with zipfile.ZipFile(NEW / "ENTREGA_POLICIA_KDE.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("CORRIDOR_COVERAGE_200M.json", archive.namelist())
            self.assertIn("ESCENARIO_FINAL_183.gpkg", archive.namelist())
        js = (ROOT / "riobamba-camaras-propuesta.js").read_text(encoding="utf-8")
        self.assertIn(NEW.name+"/", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
