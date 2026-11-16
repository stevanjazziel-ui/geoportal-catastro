import unittest
import numpy as np
from uniform_payload_codec import encode, decode


class UniformCodecTests(unittest.TestCase):
    def test_increases_decreases_and_independent_maxima_roundtrip(self):
        water = np.array([[0, 0, 0], [12, 7, 20], [4, 10, 2], [3, 0, 25]], dtype='<u2')
        maxima = np.array([[0, 0, 0], [18, 8, 22], [18, 13, 22], [18, 13, 28]], dtype='<u2')
        original = np.concatenate([water, maxima])
        np.testing.assert_array_equal(decode(encode(original, 4), 4), original)

    def test_overflow_does_not_wrap_silently(self):
        with self.assertRaises(ValueError):
            encode(np.array([[0], [40000], [0], [40000]], dtype='<u2'), 2)


if __name__ == '__main__':
    unittest.main()
