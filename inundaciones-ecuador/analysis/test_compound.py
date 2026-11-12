import unittest
import numpy as np
from compound_forcing import CompoundForcing
from hydraulics import simulate
class CompoundTests(unittest.TestCase):
 def test_river_volume(self):
  c={'surface_exchange':[{'id':'r','kind':'river_inflow','cells':[[2,2]],'seconds':[0,60],'m3_s':[1,1],'source':'synthetic numerical test'}]}
  f=CompoundForcing(c,(5,5),'test datum',60)
  r=simulate(np.ones((5,5))*10,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=1/60,boundary='closed',snapshot_minutes=1,external=f)
  self.assertAlmostEqual(r['stats']['final_storage_m3'],60,places=7)
  self.assertLess(r['stats']['mass_relative_error'],1e-8)
 def test_datum_rejected(self):
  c={'stage_boundaries':[{'side':'west','vertical_reference':'MLWS','datum_evidence':'none','seconds':[0,60],'stage_m':[1,1],'source':'test'}]}
  with self.assertRaises(ValueError):CompoundForcing(c,(5,5),'EGM96',60)
 def test_stage_mass(self):
  c={'stage_boundaries':[{'side':'west','vertical_reference':'test','datum_evidence':'synthetic shared reference','seconds':[0,60],'stage_m':[11,11],'source':'synthetic numerical test'}]}
  f=CompoundForcing(c,(5,5),'test',60)
  r=simulate(np.ones((5,5))*10,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=1/60,boundary='closed',snapshot_minutes=1,external=f)
  self.assertGreater(r['stats']['final_storage_m3'],0);self.assertLess(r['stats']['mass_relative_error'],1e-8)
 def test_sewer_cannot_remove_unavailable_water(self):
  c={'surface_exchange':[{'id':'s','kind':'swmm_prescribed_exchange','cells':[[2,2]],'seconds':[0,60],'m3_s':[-100,-100],'source':'synthetic numerical test'}]}
  f=CompoundForcing(c,(5,5),'test',60);h=np.zeros((5,5));h[2,2]=.1
  v=f.apply(h,np.ones((5,5),bool),100,60,0)
  self.assertAlmostEqual(v,-10);self.assertGreaterEqual(h.min(),0)
 def test_subsea_bed_with_explicit_mask(self):
  c={'stage_boundaries':[{'side':'west','vertical_reference':'test','datum_evidence':'synthetic shared reference','seconds':[0,60],'stage_m':[0,0],'source':'synthetic numerical test'}]}
  f=CompoundForcing(c,(5,5),'test',60)
  r=simulate(np.ones((5,5))*-1,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=1/60,boundary='closed',snapshot_minutes=1,external=f,domain_mask=np.ones((5,5),bool))
  self.assertGreater(r['stats']['final_storage_m3'],0);self.assertLess(r['stats']['mass_relative_error'],1e-8)
 def test_hydrograph_knot_is_timestep_event(self):
  c={'surface_exchange':[{'id':'r','kind':'river_inflow','cells':[[2,2]],'seconds':[0,7,60],'m3_s':[0,2,0],'source':'synthetic numerical test'}]}
  f=CompoundForcing(c,(5,5),'test',60)
  r=simulate(np.ones((5,5))*10,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=1/60,boundary='closed',snapshot_minutes=1,external=f)
  self.assertAlmostEqual(r['stats']['final_storage_m3'],60,places=7)
 def test_interval_end_exchange_preserves_step_volume(self):
  c={'surface_exchange':[{'id':'s','kind':'swmm_prescribed_exchange','cells':[[2,2]],'seconds':[0,7,60],'m3_s':[0,2,1],'interpolation':'interval_end','source':'synthetic exported step rates'}]}
  f=CompoundForcing(c,(5,5),'test',60)
  r=simulate(np.ones((5,5))*10,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=1/60,boundary='closed',snapshot_minutes=1,external=f)
  self.assertAlmostEqual(r['stats']['final_storage_m3'],67,places=7)
if __name__=='__main__':unittest.main()
