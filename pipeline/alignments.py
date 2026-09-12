"""Fetch and simplify NHAI road alignments into something a globe can draw.

Run this OCCASIONALLY, not daily:

    python3 -m pipeline.alignments

Road shapes do not change from day to day - a highway's route is fixed once it
is built. The daily refresh reads the committed output of this command and never
re-downloads it. That matters because the source layer is ~176 MB and the
GeoServer is a fragile, undocumented public endpoint that has timed out on large
requests; hitting it every morning would be both wasteful and rude.

The download is paged and each page is simplified before the next is requested,
so peak memory stays small even though the full layer is very large.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from .core import schema
from .core.fetch import fetch as http_fetch
from .core.simplify import DEFAULT_MIN_SEGMENT_KM, DEFAULT_TOLERANCE, simplify_multiline

BASE = "https://datalakew.nhai.gov.in/geoserver/NHAI/ows"
LAYER = "NHAI:upc_based_allignment_of_nhai_projects"
PAGE = 40                      # a page of 60 was ~10.5 MB; 40 keeps each request modest
OUT = os.path.join("data", "derived", "alignments.geojson")


def _page_url(start: int, count: int) -> str:
    return (
        "%s?service=WFS&version=2.0.0&request=GetFeature&typeName=%s"
        "&outputFormat=application/json&count=%d&startIndex=%d"
        "&sortBy=upc" % (BASE, LAYER, count, start)
    )


def build(tolerance: float = DEFAULT_TOLERANCE,
          min_segment_km: float = DEFAULT_MIN_SEGMENT_KM,
          limit: int = 0) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    seen_upc = set()
    start = 0
    v_before = v_after = 0
    pages = 0

    while True:
        url = _page_url(start, PAGE)
        res = http_fetch(url, delay=2.0, timeout=120, use_cache=True)
        if not res.ok:
            raise RuntimeError("alignment page at %d failed: %s (%s)" % (start, res.outcome, res.note))
        try:
            data = res.json()
        except ValueError as e:
            raise RuntimeError("alignment page at %d was not JSON: %s" % (start, e))

        batch = data.get("features") or []
        if not batch:
            break
        pages += 1

        for f in batch:
            props = f.get("properties") or {}
            geom = f.get("geometry")
            upc = props.get("upc")
            if not upc or upc in seen_upc or not geom:
                continue
            raw = geom.get("coordinates") or []
            if geom.get("type") == "LineString":
                raw = [raw]
            elif geom.get("type") != "MultiLineString":
                continue

            v_before += sum(len(l) for l in raw)
            pieces = simplify_multiline(raw, tolerance=tolerance, min_segment_km=min_segment_km)
            if not pieces:
                continue
            v_after += sum(len(p) for p in pieces)
            seen_upc.add(upc)
            features.append({
                "type": "Feature",
                "geometry": {"type": "MultiLineString",
                             "coordinates": [[list(p) for p in piece] for piece in pieces]},
                # Only the join key and enough to debug by eye. Everything the UI
                # shows about a project comes from projects.geojson, keyed on upc.
                "properties": {"upc": upc, "state": props.get("state")},
            })

        print("  page %-3d start=%-5d kept %d alignments (%s -> %s vertices)"
              % (pages, start, len(features), format(v_before, ","), format(v_after, ",")))

        if limit and len(features) >= limit:
            break
        if len(batch) < PAGE:
            break
        start += PAGE

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "generated_at": schema.utcnow(),
        "source": {
            "name": "NHAI Data Lake GeoServer",
            "layer": LAYER,
            "url": BASE,
            "note": ("Alignments simplified for display: each piece reduced with "
                     "Douglas-Peucker at %s degrees (~%d m) and pieces shorter than "
                     "%.1f km dropped. Pieces are never joined - the source splits "
                     "each highway into many disjoint segments and chaining them "
                     "invents road that does not exist."
                     % (tolerance, int(tolerance * 111320), min_segment_km)),
        },
    }
    return {"fc": fc, "v_before": v_before, "v_after": v_after}


def main(argv: List[str]) -> int:
    limit = int(argv[0]) if argv else 0
    print("Fetching NHAI alignments (this is slow and only needs doing occasionally)")
    out = build(limit=limit)
    fc = out["fc"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT)
    print("\nalignments : %d" % len(fc["features"]))
    print("vertices   : %s -> %s (%.2f%% kept)"
          % (format(out["v_before"], ","), format(out["v_after"], ","),
             100.0 * out["v_after"] / max(1, out["v_before"])))
    print("written    : %s (%.0f KB)" % (OUT, size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
