"""Turn the store into static files the globe can load.

Deliberately static: no API server, no database in production. The frontend
fetches a handful of JSON files from a CDN, which is free, fast, cacheable, and
cannot fall over. When the dataset outgrows this (roughly past ~50k features)
the answer is vector tiles (pmtiles), not a backend. See docs/adr/0003-storage.md.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import schema

OUT_DIR = os.path.join("data", "derived")

# Fields carried into the map layer. Kept small: this file is downloaded by
# every visitor, so detail lives in projects.json and is fetched on click.
FEATURE_FIELDS = (
    "id", "title", "sector", "status", "is_blocked", "block_reason",
    "cost_inr_crore", "progress_pct", "delay_months", "revised_completion_date",
    # Published so the frontend can gate the slip figure per record: only some
    # sources publish a baseline, and a missing slip must never read as "on time".
    "original_completion_date", "cost_overrun_pct",
    # The source's own key. Published so the frontend can join a project to its
    # real road alignment in alignments.geojson, which is keyed on NHAI's upc.
    "native_id",
)


def _load_supersedes() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ref",
                        "paimana_supersedes.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("supersedes") or {}
    except (IOError, ValueError):
        return {}


def publish(records: List[Dict[str, Any]], changes: List[Dict[str, Any]],
            sources: List[Dict[str, Any]], out_dir: str = OUT_DIR,
            include_unverified: bool = True) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)

    # A hand-entered seed is dropped once the real source carries the same
    # project, so the two do not both appear on the globe.
    supersedes = _load_supersedes()
    present = {r["id"] for r in records}
    by_native = {}
    for r in records:
        if r.get("native_id"):
            by_native[str(r["native_id"])] = r["id"]
    superseded = set()
    for seed_id, info in supersedes.items():
        if seed_id in present and str(info.get("paimana_id")) in by_native:
            superseded.add(seed_id)

    kept, unlocated, dropped_unverified = [], [], []
    for r in records:
        if r["id"] in superseded:
            continue
        if not include_unverified and "unverified" in (r.get("tags") or []):
            dropped_unverified.append(r["id"])
            continue
        if not ((r.get("geo") or {}).get("point")):
            # Previously dropped silently. These are real projects the sources
            # simply do not place - mostly rail corridors crossing several states,
            # where putting them on one state's dot would be a false claim. They
            # are published as an explicit list and counted in every total.
            unlocated.append(r)
            continue
        kept.append(r)

    points, lines = [], []
    for r in kept:
        props = {k: r.get(k) for k in FEATURE_FIELDS}
        geo = r["geo"]
        props["state"] = (geo.get("admin") or {}).get("state")
        props["geo_confidence"] = geo.get("geo_confidence")
        props["unverified"] = "unverified" in (r.get("tags") or [])
        points.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": geo["point"]},
            "properties": props,
        })
        if geo.get("geometry"):
            lines.append({
                "type": "Feature",
                "geometry": geo["geometry"],
                "properties": {"id": r["id"], "title": r.get("title"),
                               "sector": r.get("sector"), "status": r.get("status"),
                               "is_blocked": r.get("is_blocked")},
            })

    details = {r["id"]: _detail(r) for r in kept}

    meta = {
        "generated_at": schema.utcnow(),
        "schema_version": schema.SCHEMA_VERSION,
        "counts": {
            "published": len(kept),
            "total_in_store": len(records),
            "unlocated": len(unlocated),
            "superseded": len(superseded),
            "with_baseline": sum(1 for r in kept if r.get("original_completion_date")),
            "slip_computable": sum(1 for r in kept if r.get("delay_months") is not None),
            "by_source": _by_source(kept),
            "dropped_no_geometry": 0,
            "dropped_unverified": len(dropped_unverified),
            "corridors": len(lines),
            "blocked": sum(1 for r in kept if r.get("is_blocked")),
        },
        "by_sector": _tally(kept, "sector"),
        "by_status": _tally(kept, "status"),
        "geo_confidence": _tally_geo(kept),
        "sources": sources,
        "vocab": {
            "sectors": list(schema.SECTORS),
            "statuses": list(schema.STATUSES),
            "building_statuses": list(schema.BUILDING_STATUSES),
            "blocked_statuses": list(schema.BLOCKED_STATUSES),
            "block_reasons": list(schema.BLOCK_REASONS),
        },
        "disclaimer": (
            "Aggregated from public Government of India sources. Figures are as "
            "reported by the source on the retrieval date shown on each record and "
            "may be out of date or incorrect at source. Not investment advice."
        ),
    }

    _write(os.path.join(out_dir, "projects.geojson"),
           {"type": "FeatureCollection", "features": points})
    _write(os.path.join(out_dir, "corridors.geojson"),
           {"type": "FeatureCollection", "features": lines})
    _write(os.path.join(out_dir, "details.json"), details)
    _write(os.path.join(out_dir, "changes.json"), changes[:500])
    _write(os.path.join(out_dir, "unlocated.json"),
           [_unlocated_entry(r) for r in unlocated])
    _write(os.path.join(out_dir, "meta.json"), meta)
    return meta


def _detail(r: Dict[str, Any]) -> Dict[str, Any]:
    keep = (
        "id", "title", "description", "sector", "subsector", "status",
        "status_detail", "is_blocked", "block_reason", "block_detail",
        "cost_inr_crore", "cost_original_inr_crore", "cost_overrun_pct",
        "sanctioned_date", "original_completion_date", "revised_completion_date",
        "commissioned_date", "delay_months", "progress_pct",
        "executing_agency", "ministry", "proponent", "provenance",
        "first_seen", "last_seen", "last_changed", "tags",
    )
    d = {k: r.get(k) for k in keep}
    geo = r.get("geo") or {}
    d["admin"] = geo.get("admin")
    d["geo_confidence"] = geo.get("geo_confidence")
    d["geo_method"] = geo.get("geo_method")
    d["geo_note"] = geo.get("geo_note")
    d["history"] = r.get("history") or []
    return d


def _by_source(records: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        prov = r.get("provenance") or [{}]
        k = prov[0].get("source_id") or "unknown"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _unlocated_entry(r: Dict[str, Any]) -> Dict[str, Any]:
    d = _detail(r)
    d["states"] = [t.split(":", 1)[1] for t in (r.get("tags") or []) if t.startswith("state:")]
    d["why"] = ("crosses more than one state, so placing it on a single point would be a false claim"
                if "multi_state" in (r.get("tags") or [])
                else "no place name in the title that we could resolve")
    return d


def _tally(records: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        k = r.get(field) or "unknown"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _tally_geo(records: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        k = ((r.get("geo") or {}).get("geo_confidence")) or "none"
        out[k] = out.get(k, 0) + 1
    return out


def _write(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
