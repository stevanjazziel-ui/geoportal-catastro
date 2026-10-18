"""Independent checks for the approved public geometry, buffers and source protection."""
import unittest
import json
from pathlib import Path
import pyogrio
from shapely import union_all

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/REUNION_MUNICIPALES_BOYACA_20261017'
REVIEW = Path('D:/codex/entregas/BOYACA_DOS_CAMARAS_1_A_7_REVISION_20261017/BOYACA_DOS_CAMARAS_REVISION.gpkg')

def read(path, layer): return pyogrio.read_dataframe(path, layer=layer)

class ApprovedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = RELEASE / 'ESCENARIO_FINAL_183.gpkg'
        cls.e = read(cls.package, 'CAMARAS_EXISTENTES_103_FINAL')
        cls.m = read(cls.package, 'PROPUESTA_MUNICIPAL_50_FINAL')
        cls.p = read(cls.package, 'PROPUESTA_POLICIA_30_FINAL')

    def test_all_approved_points_match_exactly(self):
        for frame, source, key in [(self.e, 'EXISTENTES_103_INTACTAS', 'ID_CAMARA'), (self.m, 'MUNICIPALES_DESPUES_PROPUESTAS_50', 'ID_PROPUESTA'), (self.p, 'POLICIA_REUNION_30_PN27_BANCO', 'ID_REVISION')]:
            expected = read(REVIEW, source).set_index(key).loc[frame[key]]
            self.assertEqual(frame.geometry.to_wkb().tolist(), expected.geometry.to_wkb().tolist())

    def test_counts_and_documentary_ids(self):
        self.assertEqual([len(self.e), len(self.m), len(self.p)], [103, 50, 30])
        self.assertEqual(self.m.GRUPO.value_counts().to_dict(), dict(RED_ESTRUCTURAL=24, CABECERA_RURAL=22, LAS_ABRAS=4))
        self.assertEqual(set(self.p.ID_POLICIA), {'PN-' + str(i).zfill(2) for i in range(1, 32) if i != 13})
        self.assertEqual(int(self.e.REQUIERE_CAMBIO.sum()), 30)
        self.assertEqual(int(self.e.ESTADO_GEO.eq('PENDIENTE_VALIDACION').sum()), 19)

    def test_macaji_and_global_buffers(self):
        for code, frames in [('A', [self.e]), ('B', [self.e, self.m]), ('C', [self.e, self.m, self.p])]:
            expected = union_all([p.buffer(200, quad_segs=64) for f in frames for p in f.geometry])
            actual = read(self.package, 'COBERTURA_' + code).geometry.iloc[0]
            self.assertLess(expected.symmetric_difference(actual).area, .01)
        corridors = read(self.package, 'CORREDORES')
        macaji = corridors.loc[corridors.CORREDOR.eq('BOULEVARD_MACAJI_BELLAVISTA')].geometry.union_all()
        self.assertLessEqual(macaji.difference(read(self.package, 'COBERTURA_B').geometry.iloc[0]).length, .01)

    def test_exception_is_explicit_not_fake_pass(self):
        results = json.loads((RELEASE / 'RESULTADOS.json').read_text())
        self.assertTrue(results['approvedExceptions'])
        self.assertFalse(results['bridge']['physicalVisionVerified'])
        self.assertFalse(results['bridge']['giRecalculated'])
        self.assertTrue(all(not r['passed'] for r in results['bridge']['nodeAudit']))
        self.assertNotIn('global400mRevisionApplied', results)

if __name__ == '__main__': unittest.main()
