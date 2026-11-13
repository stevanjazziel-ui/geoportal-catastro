import unittest
import numpy as np
from local_flood_solver import simulate


class LocalFloodTests(unittest.TestCase):
 def test_uniform_rain_spatial_infiltration_analytical(self):
  z=np.ones((8,8))*100;mask=np.ones(z.shape,bool);loss=np.ones_like(z)*10;loss[:4]=5
  r=simulate(z,mask,20,.05,loss,[[0,30]],1,boundary='closed',snapshot_minutes=60)
  self.assertAlmostEqual(r['stats']['final_m3'],(.025*32+.020*32)*400,places=6)
 def test_mask_boundary_mass_and_no_data_not_zero_bed(self):
  z=np.ones((8,8))*100;mask=np.ones(z.shape,bool);mask[3:5,3:5]=False;z[~mask]=-9999
  r=simulate(z,mask,20,.05,0,[[0,30]],.1,boundary='open')
  self.assertGreater(r['stats']['boundary_outflow_m3'],0);self.assertEqual(r['frames'][-1][~mask].sum(),0);self.assertLess(r['stats']['mass_relative_error'],1e-8)
 def test_masked_lake_at_rest(self):
  z=np.ones((8,8))*100;z[:,4:]=100.2;mask=np.ones(z.shape,bool);mask[0,0]=False;initial=101-z;initial[~mask]=0
  r=simulate(z,mask,20,.05,0,[[0,0]],.05,boundary='closed',initial=initial)
  np.testing.assert_allclose(r['frames'][-1],initial,atol=1e-7)
 def test_prescribed_network_overflow_volume(self):
  z=np.ones((5,5))*100;mask=np.ones(z.shape,bool)
  r=simulate(z,mask,20,.05,0,[[0,0]],1/60,boundary='closed',source_times=[0,7,60],source_rates=[[0],[2],[1]],source_cells=[[2,2]])
  self.assertAlmostEqual(r['stats']['final_m3'],67,places=7)


if __name__=='__main__':unittest.main()
