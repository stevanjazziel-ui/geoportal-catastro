import unittest
import numpy as np
from hydraulics import simulate
from build_data import drainage_hand

class HydraulicTests(unittest.TestCase):
    def test_uniform_closed_rain_matches_analytical_depth(self):
        z=np.ones((8,8))*10
        r=simulate(z,50,rain_mm_h=60,rain_hours=1,duration_hours=1,infiltration_mm_h=0,boundary='closed')
        np.testing.assert_allclose(r['frames'][-1],.06,atol=1e-10)
        self.assertLess(r['stats']['mass_relative_error'],1e-10)
    def test_lake_at_rest_preserves_surface_and_mass(self):
        z=np.tile(np.linspace(10,11,8),(8,1));h=12-z
        r=simulate(z,50,rain_mm_h=0,infiltration_mm_h=0,duration_hours=.1,boundary='closed',initial_depth=h,snapshot_minutes=3)
        np.testing.assert_allclose(r['frames'][-1],h,atol=1e-8)
        self.assertLess(r['stats']['mass_relative_error'],1e-10)
    def test_free_drainage_mass_and_positivity(self):
        z=np.tile(np.linspace(12,10,12),(12,1))
        r=simulate(z,50,rain_mm_h=100,rain_hours=.1,duration_hours=.2,infiltration_mm_h=5,snapshot_minutes=3)
        self.assertGreater(r['stats']['outflow_m3'],0)
        self.assertGreaterEqual(np.min(r['frames'][-1]),0)
        self.assertLess(r['stats']['mass_relative_error'],1e-8)
    def test_missing_dem_rejected(self):
        z=np.ones((4,4));z[1,1]=np.nan
        with self.assertRaises(ValueError):simulate(z,50)
    def test_no_channel_is_unknown_not_low_hand(self):
        z=np.ones((8,8))*10
        hand,ch,_,_=drainage_hand(z,10,threshold_km2=100)
        self.assertFalse(ch.any());self.assertTrue(np.isnan(hand).all())
    def test_hand_zero_at_derived_channels(self):
        y,x=np.indices((20,20));z=100+np.abs(x-10)*3-y*.1
        hand,ch,_,_=drainage_hand(z,100,threshold_km2=.05)
        self.assertTrue(ch.any());np.testing.assert_allclose(hand[ch],0)

if __name__=='__main__':unittest.main()
