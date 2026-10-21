import unittest

from shapely.geometry import Point, box
from shapely.ops import unary_union

from build_camera_population_comparison import population_comparison


class PopulationComparisonTest(unittest.TestCase):
    def test_partitions_overlap_missing_population_and_urban_clip(self):
        existing = [(Point(0, 0), {"REQUIERE_CAMBIO": False})] * 73
        existing += [(Point(1000, 0), {"REQUIERE_CAMBIO": True})] * 30
        proposed = [(Point(1000, 0), {})]
        urban = unary_union([box(-10, -10, 10, 10), box(990, -10, 1010, 10)])
        blocks = [(box(-20, -10, 20, 10), {"POBLACION": 200}),
                  (box(990, -10, 1010, 10), {"POBLACION": 200}),
                  (box(-5, -5, 5, 5), {"POBLACION": None}),
                  (box(-5, -5, 5, 5), {"POBLACION": float("nan")}),
                  (box(2000, 0, 2010, 10), {"POBLACION": 900})]
        result = population_comparison(existing, proposed * 50, proposed * 30, blocks, urban)
        self.assertAlmostEqual(result["analyzedPopulation"], 300)
        self.assertAlmostEqual(result["scenarios"][0]["coveredPopulation"], 100)
        self.assertAlmostEqual(result["scenarios"][1]["coveredPopulation"], 300)
        self.assertAlmostEqual(result["additionalPopulation"], 200)
        self.assertAlmostEqual(result["percentagePointGain"], 200 / 3)
        self.assertEqual(result["blocksWithoutPopulation"], 2)

    def test_rejects_wrong_camera_partition(self):
        with self.assertRaises(ValueError):
            population_comparison([], [], [], [], box(0, 0, 1, 1))


if __name__ == "__main__":
    unittest.main()
