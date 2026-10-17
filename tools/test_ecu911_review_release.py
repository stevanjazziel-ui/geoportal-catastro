"""Read-only regression checks for the approved ECU911 release."""
import unittest
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_ecu911_review_20261017 as release
from bridge.store import read_json


class Ecu911ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = gpd.read_file(release.OUT/'ESCENARIO_FINAL_183.gpkg', layer='CAMARAS_EXISTENTES_103_FINAL').set_index('ID_CAMARA')
        cls.original = gpd.read_file(release.REVIEW/'ORIGINALES/CAMARAS_103_PARA_CODEX.gpkg').set_index('ID')

    def test_74_documented_are_byte_identical(self):
        locked = self.original.loc[self.original.ESTADO_XY.eq('DOCUMENTADA')]
        self.assertEqual(len(locked), 74)
        self.assertEqual(locked.geometry.to_wkb().tolist(), self.frame.loc[locked.index].geometry.to_wkb().tolist())

    def test_only_four_input_geometries_change(self):
        moved = {key for key in self.original.index if self.original.loc[key].geometry.wkb != self.frame.loc[key].geometry.wkb}
        self.assertEqual(moved, {'RIO-084-DOMO','RIO-085-DOMO','RIO-099-DOMO','RIO-100-FIJA'})

    def test_pending_do_not_silently_become_verified(self):
        pending = self.frame.loc[self.frame.ESTADO_GEO.eq('PENDIENTE_VALIDACION')]
        self.assertEqual(len(pending), 19)
        self.assertEqual(pending.geometry.to_wkb().tolist(), self.original.loc[pending.index].geometry.to_wkb().tolist())
        self.assertTrue(pending.CONFIANZA_GEO.eq('INSUFICIENTE').all())

    def test_distinct_camera_ids_can_share_intersection(self):
        self.assertEqual(len(self.frame), 103)
        self.assertTrue(self.frame.index.is_unique)
        self.assertEqual(int(self.frame.REQUIERE_CAMBIO.sum()), 30)
        self.assertEqual(self.frame.loc['RIO-099-DOMO'].geometry.wkb, self.frame.loc['RIO-100-FIJA'].geometry.wkb)

    def test_rio084_is_exactly_the_approved_node(self):
        candidate = gpd.read_file(release.CANDIDATE, layer='CANDIDATO_NO_INCORPORADO').geometry.iloc[0]
        self.assertEqual(self.frame.loc['RIO-084-DOMO'].geometry.wkb, candidate.wkb)
        self.assertNotEqual(self.frame.loc['RIO-084-DOMO'].geometry.wkb, self.frame.loc['RIO-031-DOMO'].geometry.wkb)

    def test_overlay_exposes_provisional_status(self):
        gaps = read_json(release.OUT/'coverage-inputs/RESULTADOS.json')
        overlay = gaps['inventoryCameraOverlay']
        self.assertEqual(len(overlay), 103)
        self.assertEqual(sum(row['provisional'] for row in overlay), 19)
        self.assertEqual(sum(row['requiresChange'] for row in overlay), 30)
        self.assertTrue(gaps['metadata']['inventoryGeolocation']['coverageIncludesProvisionalPositions'])


if __name__ == '__main__':
    unittest.main()
