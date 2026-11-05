import unittest

from plugin.wavefront_engine import _clip_ring_to_region


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Ring:
    def __init__(self, points):
        self.points = [Point(x, y) for x, y in points]


class Rect:
    def __init__(self, xmin, ymin, xmax, ymax):
        self.bounds = (xmin, ymin, xmax, ymax)

    def contains(self, point):
        xmin, ymin, xmax, ymax = self.bounds
        return xmin <= point.x <= xmax and ymin <= point.y <= ymax


class WavefrontClippingTests(unittest.TestCase):
    def test_fully_inside_ring_keeps_original_vertices(self):
        ring = Ring([(0, 0), (100, 0), (100, 100), (0, 100)])
        paths = _clip_ring_to_region(ring, [Rect(-10, -10, 110, 110)], 5, Point)
        self.assertEqual(len(paths), 1)
        self.assertEqual(len(paths[0]), 5)
        self.assertEqual(paths[0][0], paths[0][-1])

    def test_clipping_splits_ring_at_region_boundary(self):
        ring = Ring([(0, 0), (100, 0), (100, 100), (0, 100)])
        paths = _clip_ring_to_region(ring, [Rect(-10, -10, 50, 110)], 5, Point)
        self.assertGreaterEqual(len(paths), 1)
        for path in paths:
            for x, y in path:
                self.assertLessEqual(x, 50)

    def test_too_small_rings_are_ignored(self):
        ring = Ring([(0, 0), (10, 0)])
        self.assertEqual(
            _clip_ring_to_region(ring, [Rect(-1, -1, 11, 1)], 1, Point),
            []
        )


if __name__ == "__main__":
    unittest.main()
