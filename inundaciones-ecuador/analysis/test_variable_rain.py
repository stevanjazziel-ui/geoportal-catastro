import unittest
import numpy as np
from variable_riobamba import hyetograph,conservative_series

class VariableRainTests(unittest.TestCase):
    def test_station_depths_and_peak_duration(self):
        for ret,total,peak in [(25,42.6,103.4),(50,48.6,119.6),(100,55.2,138.4)]:
            h=hyetograph(ret);rates=np.array(h['intensities_mm_h'])
            self.assertAlmostEqual(float(np.dot(rates[:-1],np.diff(h['seconds']))/3600),total)
            self.assertAlmostEqual(h['peak_mm_h'],peak)
            self.assertEqual(int(np.argmax(rates)),18)
            self.assertEqual(h['seconds'][-1],21600)
            self.assertEqual(rates[-1],0)
            self.assertTrue(all(abs(c['relative_difference'])<.002 for c in h['duration_checks']))

    def test_linear_input_preserves_each_node_volume(self):
        q=np.array([[1.,0.,3.],[4.,5.,0.],[0.,2.,7.]])
        t,rates,factor=conservative_series(q,600,7200)
        # Independent integration: 1s-resolution quadrature of each linear input.
        dense=np.arange(7201.)
        integrals=np.array([np.trapezoid(np.interp(dense,t,rates[:,i]),dense) for i in range(3)])
        np.testing.assert_allclose(integrals,[3000.,4200.,6000.],rtol=1e-10)
        self.assertLess(factor,.001)
        self.assertTrue((rates>=0).all())

if __name__=='__main__':unittest.main()
