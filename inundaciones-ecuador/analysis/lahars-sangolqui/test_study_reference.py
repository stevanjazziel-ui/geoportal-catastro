"""Analytic checks on source integration, terrain conditioning and section units."""
import unittest
import numpy as np
from study_reference import PEAKS, PIXELS, fill_depressions
from analyze_study import section_flux


class ScientificChecks(unittest.TestCase):
    def test_published_source_integrals_and_rounding(self):
        self.assertEqual(len(PIXELS),9)
        self.assertEqual(sum(PEAKS),77309)
        self.assertEqual(sum(q*900/2 for q in PEAKS),34789050)
        t=np.array([0.,150.,900.]);q=np.array([0.,sum(PEAKS),0.])
        self.assertEqual(float(np.trapezoid(q,t)),34789050)

    def test_flat_uniform_section_units_and_partition(self):
        result=section_flux(np.full(10,2.),np.full(10,3.),np.ones(10),np.full(10,.4),10)
        self.assertAlmostEqual(result['north_m3_s'],600)
        self.assertAlmostEqual(result['solids_north_m3_s'],240)
        self.assertAlmostEqual(result['water_north_m3_s'],360)
        self.assertAlmostEqual(float(np.trapezoid([600,600],[0,30])),18000)

    def test_reverse_transport_is_not_hidden(self):
        result=section_flux(np.ones(2),np.array([3.,-2.]),np.ones(2),np.zeros(2),10)
        self.assertEqual(result['north_m3_s'],30)
        self.assertEqual(result['south_m3_s'],20)
        self.assertEqual(result['net_north_m3_s'],10)

    def test_spill_conditioning_preserves_boundaries(self):
        z=np.array([[5.,5.,5.],[5.,1.,4.],[5.,5.,5.]])
        filled=fill_depressions(z)
        self.assertEqual(filled[1,1],4)
        self.assertTrue(np.array_equal(z[0],filled[0]))
        limited=np.where(filled-z<=2,filled,z)
        self.assertEqual(limited[1,1],1)


if __name__=='__main__':unittest.main()
