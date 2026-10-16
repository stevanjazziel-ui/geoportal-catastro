"""Focused checks for separation, branch handling and documented names."""
import unittest

from study_municipal_spacing_400 import bounded_routes, canonical


class SpacingTests(unittest.TestCase):
    def test_400_is_permitted_and_399_is_not(self):
        a, b, c = (0., 0.), (399., 0.), (400., 0.)
        street = {'adj': {a: {b}, b: {a, c}, c: {b}}}
        reached = bounded_routes(street, a)
        self.assertEqual(reached[b], 399.)
        self.assertNotIn(c, reached)

    def test_same_name_branch_is_not_silently_ignored(self):
        a, b, c, d = (0., 0.), (100., 0.), (200., 0.), (100., 100.)
        street = {'adj': {a: {b}, b: {a, c, d}, c: {b}, d: {b}}}
        self.assertEqual(bounded_routes(street, a)[d], 200.)

    def test_disconnected_carriageway_is_not_joined(self):
        a, b, c, d = (0., 0.), (100., 0.), (0., 5.), (100., 5.)
        street = {'adj': {a: {b}, b: {a}, c: {d}, d: {c}}}
        self.assertNotIn(c, bounded_routes(street, a))

    def test_documented_name_normalization(self):
        self.assertEqual(canonical('Av. Antonio José de Sucre'), canonical('Avenida Antonio Jose de Sucre'))


if __name__ == '__main__':
    unittest.main()
