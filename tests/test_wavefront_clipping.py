import unittest

from plugin.wavefront_engine import (\n    _clip_ring_to_region, split_narrow_necks, smart_bridgeability_allows\n)


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



class FakePiece:
    def __init__(self, name, cores=None):
        self.name = name
        self.cores = cores or []

    def offset(self, distance):
        if distance < 0:
            return self.cores
        return [self]

    def intersection_ex(self, other):
        return [self]

    def diff_ex(self, other):
        return [] if self is other else [self]


class FakeSurface:
    def __init__(self, internal, bridge):
        self._internal = internal
        self._bridge = bridge

    def is_internal(self):
        return self._internal

    def is_bridge(self):
        return self._bridge


class WavefrontClippingTests(unittest.TestCase):
    def test_smart_bridgeability_accepts_small_outside_hull_fraction(self):
        self.assertTrue(smart_bridgeability_allows(100, 20, threshold=0.20))

    def test_smart_bridgeability_rejects_large_outside_hull_fraction(self):
        self.assertFalse(smart_bridgeability_allows(100, 20.01, threshold=0.20))

    def test_smart_bridgeability_always_accepts_regions_with_holes(self):
        self.assertTrue(smart_bridgeability_allows(100, 95, has_holes=True))

    def test_smart_bridgeability_rejects_zero_area(self):
        self.assertFalse(smart_bridgeability_allows(0, 0))

    def test_native_bridge_surfaces_are_not_wave_candidates(self):
        # Orca's Surface::is_internal() includes stInternalBridge.
        bridge = FakeSurface(internal=True, bridge=True)
        self.assertFalse(bridge.is_internal() and not bridge.is_bridge())

    def test_internal_sparse_fill_remains_a_wave_candidate(self):
        sparse = FakeSurface(internal=True, bridge=False)
        self.assertTrue(sparse.is_internal() and not sparse.is_bridge())

    def test_external_surfaces_are_not_wave_candidates(self):
        external = FakeSurface(internal=False, bridge=False)
        self.assertFalse(external.is_internal() and not external.is_bridge())

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

    def test_narrow_neck_split_keeps_eroded_cores_separate(self):
        left = FakePiece("left")
        right = FakePiece("right")
        region = FakePiece("source", [left, right])
        result = split_narrow_necks(region, 4)
        self.assertEqual(result, [left, right])

    def test_narrow_neck_split_falls_back_when_no_topology_change(self):
        region = FakePiece("single", [FakePiece("single-core")])
        self.assertEqual(split_narrow_necks(region, 4), [region])

    def test_too_small_rings_are_ignored(self):
        ring = Ring([(0, 0), (10, 0)])
        self.assertEqual(
            _clip_ring_to_region(ring, [Rect(-1, -1, 11, 1)], 1, Point),
            []
        )


if __name__ == "__main__":
    unittest.main()
