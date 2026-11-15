import unittest
import numpy as np
from local_flood_solver import simulate


class UniformPrefixTests(unittest.TestCase):
    def test_prefix_matches_independent_shorter_calculation(self):
        yy, xx = np.mgrid[:9, :11]
        z = .08 * xx + .025 * yy + .1 * np.sin(xx)
        mask = np.ones(z.shape, bool)
        mask[2, 3] = False
        n = .04 + xx * .001
        rates = np.array([[0.], [.005], [.01], [0.], [0.]])
        source = dict(source_times=[0, 900, 1800, 2700, 3600], source_rates=rates, source_cells=[[4, 4]])
        full = simulate(z, mask, 5, n, 1., [[0, 75], [3600, 0]], 1.,
                        snapshot_minutes=15, record_prefixes=True, **source)
        self.assertEqual(len(full['max_frames']), 5)
        for i, minutes in enumerate([15, 30, 45, 60], 1):
            short = simulate(z, mask, 5, n, 1., [[0, 75], [minutes * 60, 0]], minutes / 60,
                             snapshot_minutes=15, **source)
            np.testing.assert_allclose(full['frames'][i], short['frames'][-1], atol=1e-8)
            np.testing.assert_allclose(full['max_frames'][i], short['max_depth'], atol=1e-7)
            self.assertAlmostEqual(full['prefix_stats'][i]['max_depth_m'], short['stats']['max_depth_m'], places=9)
            self.assertAlmostEqual(full['prefix_stats'][i]['max_footprint_km2'], short['stats']['max_footprint_km2'])
            self.assertLess(full['prefix_stats'][i]['mass_relative_error'], 1e-8)
            self.assertAlmostEqual(full['prefix_stats'][i]['direct_rain_m3'], 75 / 1000 * minutes / 60 * mask.sum() * 25, places=7)

    def test_recording_does_not_change_hydraulics(self):
        z = np.tile(np.arange(7) * .05, (7, 1))
        args = (z, np.ones(z.shape, bool), 5, .04, 2., [[0, 15.6], [1800, 0]], .5)
        plain = simulate(*args)
        recorded = simulate(*args, record_prefixes=True)
        np.testing.assert_array_equal(plain['frames'], recorded['frames'])
        self.assertEqual(plain['stats'], recorded['stats'])
        self.assertNotIn('prefix_stats', plain)


if __name__ == '__main__':
    unittest.main()
