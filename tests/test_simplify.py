"""Tests for road-geometry simplification."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.core.simplify import (
    douglas_peucker, simplify_multiline, dedupe, path_length_km, haversine_km,
)


class TestDouglasPeucker(unittest.TestCase):
    def test_straight_line_collapses_to_endpoints(self):
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
        self.assertEqual(douglas_peucker(pts, 0.001), [(0.0, 0.0), (3.0, 0.0)])

    def test_a_real_corner_survives(self):
        pts = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        self.assertEqual(len(douglas_peucker(pts, 0.001)), 3)

    def test_endpoints_are_always_kept(self):
        pts = [(float(i), (i % 2) * 0.0001) for i in range(50)]
        out = douglas_peucker(pts, 0.01)
        self.assertEqual(out[0], pts[0])
        self.assertEqual(out[-1], pts[-1])

    def test_tolerance_controls_aggressiveness(self):
        pts = [(i * 0.1, (0.02 if i % 2 else 0.0)) for i in range(200)]
        self.assertGreater(len(douglas_peucker(pts, 0.001)), len(douglas_peucker(pts, 0.5)))

    def test_short_inputs_pass_through(self):
        self.assertEqual(douglas_peucker([], 0.01), [])
        self.assertEqual(douglas_peucker([(1.0, 2.0)], 0.01), [(1.0, 2.0)])
        self.assertEqual(douglas_peucker([(1.0, 2.0), (3.0, 4.0)], 0.01), [(1.0, 2.0), (3.0, 4.0)])

    def test_handles_very_long_input_without_recursion_error(self):
        # Real alignments reach ~50k vertices in one piece. A recursive
        # implementation dies here; this is why the algorithm is iterative.
        pts = [(i * 0.0001, (i % 7) * 0.00002) for i in range(60000)]
        out = douglas_peucker(pts, 0.001)
        self.assertGreaterEqual(len(out), 2)
        self.assertLess(len(out), len(pts))

    def test_output_is_a_subset_in_original_order(self):
        pts = [(0.0, 0.0), (1.0, 0.6), (2.0, 0.0), (3.0, 0.7), (4.0, 0.0)]
        out = douglas_peucker(pts, 0.1)
        self.assertEqual(out, [p for p in pts if p in out], "order must be preserved")
        for p in out:
            self.assertIn(p, pts, "simplification must never invent a point")


class TestSimplifyMultiline(unittest.TestCase):
    def test_pieces_are_never_joined(self):
        """The bug this guards against: chaining disjoint pieces invents road.

        Measured on real NHAI data, naive chaining produced phantom 8-9 km
        jumps across open country. Two far-apart pieces must stay two pieces.
        """
        west = [[77.0, 28.0], [77.2, 28.0], [77.4, 28.0]]
        east = [[80.0, 28.0], [80.2, 28.0], [80.4, 28.0]]
        out = simplify_multiline([west, east], tolerance=0.001, min_segment_km=0.1)
        self.assertEqual(len(out), 2, "disjoint pieces must not be merged")
        for piece in out:
            span = haversine_km(piece[0], piece[-1])
            self.assertLess(span, 100, "no piece should span the gap between inputs")

    def test_invisible_fragments_are_dropped(self):
        tiny = [[77.0, 28.0], [77.0005, 28.0]]          # ~50 m
        real = [[77.0, 28.0], [77.5, 28.0]]             # ~49 km
        out = simplify_multiline([tiny, real], min_segment_km=1.0)
        self.assertEqual(len(out), 1)

    def test_degenerate_pieces_are_dropped(self):
        out = simplify_multiline([[[77.0, 28.0]], [], [[77.0, 28.0], [77.0, 28.0]]],
                                 min_segment_km=0.0)
        self.assertEqual(out, [])

    def test_coordinates_are_rounded_but_still_in_india(self):
        line = [[77.123456789, 28.987654321], [78.5, 29.5]]
        out = simplify_multiline([line], min_segment_km=0.0, precision=4)
        lon, lat = out[0][0]
        self.assertEqual(lon, 77.1235)
        self.assertEqual(lat, 28.9877)
        self.assertTrue(65 <= lon <= 98 and 5 <= lat <= 38)

    def test_elevation_third_ordinate_is_stripped(self):
        # NHAI ships [lon, lat, 0] triples; a third ordinate breaks the renderer.
        line = [[77.0, 28.0, 0.0], [77.5, 28.0, 0.0]]
        out = simplify_multiline([line], min_segment_km=0.0)
        for p in out[0]:
            self.assertEqual(len(p), 2)

    def test_realistic_alignment_shrinks_hard_but_keeps_shape(self):
        # A 100 km road sampled every ~50 m, with gentle curvature.
        import math
        line = [[77.0 + i * 0.0005, 28.0 + 0.25 * math.sin(i * 0.002)] for i in range(2000)]
        out = simplify_multiline([line], tolerance=0.005, min_segment_km=1.0)
        self.assertEqual(len(out), 1)
        kept = len(out[0])
        self.assertLess(kept, 200, "should discard the overwhelming majority of vertices")
        self.assertGreater(kept, 2, "a curve must not collapse to a straight line")


class TestHelpers(unittest.TestCase):
    def test_dedupe_removes_only_consecutive_repeats(self):
        self.assertEqual(dedupe([(1.0, 1.0), (1.0, 1.0), (2.0, 2.0), (1.0, 1.0)]),
                         [(1.0, 1.0), (2.0, 2.0), (1.0, 1.0)])

    def test_path_length_is_plausible(self):
        # One degree of longitude at the equator is ~111 km.
        self.assertAlmostEqual(path_length_km([(77.0, 0.0), (78.0, 0.0)]), 111.32, delta=1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
