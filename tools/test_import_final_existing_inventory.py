import unittest

import geopandas as gpd
from shapely.geometry import Point

from import_final_existing_inventory import normalize


class InventoryImportTests(unittest.TestCase):
    def setUp(self):
        ids = [f"RIO-{i:03d}-DOMO" for i in range(1, 104)]
        self.incoming = gpd.GeoDataFrame({
            "ID": ids, "ACTUALIZ": ["SI"] * 30 + ["NO"] * 73,
            "TIPO_POS": ["ESQUINA_ESTIMADA"] + ["SIN_CAMBIO"] * 102,
            "CONF_ESQ": ["NO_VERIFICADA"] + [None] * 102,
            "VALIDACION": ["DOCUMENTAL_CONSERVADA"] * 103,
        }, geometry=[Point(760000 + i, 9815000) for i in range(103)], crs=32717)
        self.previous = gpd.GeoDataFrame({
            "ID_CAMARA": ids, "REQUIERE_CAMBIO": [True] * 31 + [False] * 72,
        }, geometry=self.incoming.geometry.copy(), crs=32717)

    def test_mapping_geometry_and_source_preservation(self):
        before = self.incoming.copy()
        result, audit = normalize(self.incoming, self.previous.iloc[::-1], True)
        self.assertEqual(int(result.REQUIERE_CAMBIO.sum()), 30)
        self.assertEqual(int((~result.REQUIERE_CAMBIO).sum()), 73)
        self.assertEqual(result.geometry.to_wkb().tolist(), before.geometry.to_wkb().tolist())
        self.assertTrue(self.incoming.equals(before))
        self.assertTrue(audit.DESPLAZAMIENTO_M.eq(0).all())
        self.assertEqual(audit.loc[audit.CAMBIO_ANTERIOR != audit.CAMBIO_CONFIRMADO, "ID_CAMARA"].tolist(), ["RIO-031-DOMO"])
        self.assertEqual(result.loc[0, "CONF_ESQ"], "NO_VERIFICADA")

    def test_confirmation_required(self):
        with self.assertRaisesRegex(ValueError, "confirmacion"):
            normalize(self.incoming, self.previous)

    def test_unknown_flag_rejected(self):
        self.incoming.loc[100, "ACTUALIZ"] = "PENDIENTE"
        with self.assertRaisesRegex(ValueError, "SI/NO"):
            normalize(self.incoming, self.previous, True)

    def test_wrong_count_rejected(self):
        self.incoming.loc[30, "ACTUALIZ"] = "SI"
        with self.assertRaisesRegex(ValueError, "30"):
            normalize(self.incoming, self.previous, True)

    def test_duplicate_id_rejected(self):
        self.incoming.loc[1, "ID"] = self.incoming.loc[0, "ID"]
        with self.assertRaisesRegex(ValueError, "103 IDs"):
            normalize(self.incoming, self.previous, True)

    def test_wrong_crs_rejected(self):
        self.incoming = self.incoming.to_crs(4326)
        with self.assertRaisesRegex(ValueError, "32717"):
            normalize(self.incoming, self.previous, True)

    def test_missing_point_rejected(self):
        self.incoming.loc[0, "geometry"] = None
        with self.assertRaisesRegex(ValueError, "sin geometria"):
            normalize(self.incoming, self.previous, True)


if __name__ == "__main__":
    unittest.main()
