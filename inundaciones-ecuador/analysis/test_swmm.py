"""Integration check against the official EPA Extran example, not Ecuador field data."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from run_swmm import run
import numpy as np
from swmm_surface_exchange import export
from compound_forcing import CompoundForcing
from hydraulics import simulate


class SwmmIntegrationTests(unittest.TestCase):
    def test_epa_dynamic_wave_full_duration_and_continuity(self):
        source=Path(__file__).parent/'raw/compound-acquisition/EPA-Example2.inp'
        if not source.exists():self.skipTest('Download the official EPA example first')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent,prefix='swmm-test-') as tmp:
            output=Path(tmp)/'network'
            report=run(source,output)
            self.assertEqual(report['duration_seconds'],28800)
            self.assertEqual(len(report['nodes']),10)
            self.assertLess(abs(report['routing_continuity_error_percent']),.1)
            with (output/'nodes.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(float(rows[-1]['seconds']),28800)
            self.assertTrue(any(float(r['flood_m3_s'])>0 for r in rows))
            self.assertTrue(all(float(r['depth_m'])>=0 for r in rows))
            mapping=Path(tmp)/'mapping.json'
            mapping.write_text(json.dumps({'source':'EPA numerical example','geometry_evidence':'Synthetic cell placement for a volume-transfer check only','nodes':{'80608':[[2,2]]}}))
            forcing=export(output,mapping,Path(tmp)/'forcing.json')
            external=CompoundForcing(forcing,(5,5),'synthetic',28800)
            result=simulate(np.ones((5,5))*10,20,rain_mm_h=0,infiltration_mm_h=0,duration_hours=8,boundary='closed',external=external)
            node_rows=[r for r in rows if r['node']=='80608']
            volume=sum((float(b['seconds'])-float(a['seconds']))*float(b['flood_m3_s']) for a,b in zip(node_rows,node_rows[1:]))
            self.assertGreater(volume,0)
            self.assertAlmostEqual(result['stats']['final_storage_m3'],volume,places=6)


if __name__=='__main__':unittest.main()
