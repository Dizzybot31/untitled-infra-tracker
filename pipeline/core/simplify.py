"""Reduce road alignment geometry to what a globe can actually show.

NHAI publishes survey-grade alignments: a median of ~3,300 vertices per highway,
one with 49,872. The full layer is ~176 MB. At the zoom this product is viewed
at, one screen pixel covers roughly 5 km, so essentially all of that precision
is invisible.

Two things have to be right here, and the second is the one that bites:

  1. Simplification must preserve the road's SHAPE. Douglas-Peucker does this -
     it keeps the vertices that define the curve and discards the ones that sit
     on a line between their neighbours.

  2. Sub-segments must NOT be chained together. Each alignment arrives as a
     MultiLineString of many disjoint pieces (one has 4,762). Joining them
     end-to-end is the obvious move and it invents roads: measured against real
     data it produced phantom 8-9 km jumps across open country where no road
     exists. Each piece is simplified and kept separately.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

Point = Tuple[float, float]

# ~0.005 degrees is about 550 m. One pixel at the default camera is about 5 km,
# so this is comfortably sub-pixel; the shape is preserved, the noise is not.
DEFAULT_TOLERANCE = 0.005

# Pieces shorter than this cannot be seen and are usually slip roads, stubs, or
# digitising artefacts. Dropping them removes most of the vertex count.
DEFAULT_MIN_SEGMENT_KM = 1.0


def haversine_km(a: Point, b: Point) -> float:
    """Good enough for length screening at this scale, and cheap."""
    mean_lat = math.radians((a[1] + b[1]) / 2.0)
    dx = (b[0] - a[0]) * math.cos(mean_lat)
    dy = b[1] - a[1]
    return math.hypot(dx, dy) * 111.32


def path_length_km(pts: Sequence[Point]) -> float:
    return sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _perpendicular_distance(p: Point, a: Point, b: Point) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def douglas_peucker(pts: List[Point], tolerance: float = DEFAULT_TOLERANCE) -> List[Point]:
    """Iterative Douglas-Peucker.

    Deliberately not recursive: real alignments reach ~50k vertices in a single
    piece, which blows Python's recursion limit on a plain recursive version.
    """
    if len(pts) < 3:
        return list(pts)

    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        dmax, idx = 0.0, start
        a, b = pts[start], pts[end]
        for i in range(start + 1, end):
            d = _perpendicular_distance(pts[i], a, b)
            if d > dmax:
                dmax, idx = d, i
        if dmax > tolerance:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))

    return [p for p, k in zip(pts, keep) if k]


def dedupe(pts: Sequence[Point]) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def simplify_multiline(
    coordinates: Sequence[Sequence[Sequence[float]]],
    tolerance: float = DEFAULT_TOLERANCE,
    min_segment_km: float = DEFAULT_MIN_SEGMENT_KM,
    precision: int = 4,
) -> List[List[Point]]:
    """Simplify each piece independently. Never joins pieces together.

    Returns a list of pieces, each a list of [lon, lat] points. Pieces that are
    too short to see, or that collapse to fewer than two points, are dropped.
    """
    out: List[List[Point]] = []
    for line in coordinates:
        pts = dedupe([(round(float(p[0]), precision), round(float(p[1]), precision))
                      for p in line if len(p) >= 2])
        if len(pts) < 2:
            continue
        if path_length_km(pts) < min_segment_km:
            continue
        simplified = douglas_peucker(pts, tolerance) if len(pts) > 2 else pts
        if len(simplified) >= 2:
            out.append(simplified)
    return out


def stats(before: Sequence[Sequence[Sequence[float]]], after: Sequence[Sequence[Point]]) -> Dict[str, Any]:
    v_before = sum(len(l) for l in before)
    v_after = sum(len(l) for l in after)
    return {
        "pieces_before": len(before),
        "pieces_after": len(after),
        "vertices_before": v_before,
        "vertices_after": v_after,
        "kept_pct": round(100.0 * v_after / v_before, 2) if v_before else 0.0,
    }
