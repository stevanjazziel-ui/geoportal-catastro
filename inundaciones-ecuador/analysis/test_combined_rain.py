import unittest
import numpy as np
from combined_riobamba import catalog, hyetograph, SPEC


class CombinedRainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = catalog()

    def test_source_average_and_duration(self):
        c = self.cat
        for duration, values in c['mean_intensities_mm_h'].items():
            expected = (np.array(c['stations']['M1036']['intensities_mm_h'][duration]) +
                        np.array(c['stations']['M0057']['intensities_mm_h'][duration])) / 2
            np.testing.assert_allclose(values, expected)
        self.assertAlmostEqual(c['mean_intensities_mm_h'][60][-1], 37.5)
        self.assertAlmostEqual(c['mean_intensities_mm_h'][120][-1], 20.6)
        self.assertAlmostEqual(c['mean_intensities_mm_h'][360][-1], 7.8)
        self.assertIsNone(c['assigned_combined_return_period_years'])

    def test_integrated_volume_and_explicit_assumptions(self):
        expected = [36.9, 41.7, 46.8, 75., 93.6, 93.6]
        for name, total in zip(SPEC, expected):
            h = hyetograph(name, self.cat)
            volume = np.dot(h['intensities_mm_h'][:-1], np.diff(h['seconds'])) / 3600
            self.assertAlmostEqual(volume, total)
            self.assertAlmostEqual(h['total_mm'], total)
            self.assertEqual(h['intensities_mm_h'][-1], 0)
            self.assertEqual(h['seconds'][-1], h['duration_minutes'] * 60)
            self.assertIsNone(h['return_period_years'])
            self.assertEqual(h['preparedness_test'], name.startswith('prepared-'))
            self.assertTrue(all(abs(d['relative_difference']) < .02 for d in h['duration_checks']))

    def test_repeat_is_two_identical_storms_and_stress_is_rain_only(self):
        base = np.array(hyetograph('combined-6h-high', self.cat)['intensities_mm_h'][:-1])
        repeated = np.array(hyetograph('prepared-12h-repeat', self.cat)['intensities_mm_h'][:-1])
        doubled = np.array(hyetograph('prepared-6h-double', self.cat)['intensities_mm_h'][:-1])
        np.testing.assert_allclose(repeated[:36], base)
        np.testing.assert_allclose(repeated[36:], base)
        np.testing.assert_allclose(doubled, base * 2)


if __name__ == '__main__':
    unittest.main()
