"""Canonical project record.

Every adapter, whatever the source looks like, must emit records that validate
against this module. The globe frontend only ever sees the canonical shape.

Design rules that are not negotiable:
  1. Nothing is stored without provenance. Every record carries the source URL
     and the retrieval timestamp that produced it.
  2. Geocoding always records how it was done and how much to trust it.
  3. Status is a small closed vocabulary. Source-specific wording is preserved
     verbatim in status_detail so we never destroy the original text.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

# --- Controlled vocabularies -------------------------------------------------

SECTORS = (
    "road", "rail", "metro", "power", "renewable", "port", "airport",
    "water", "irrigation", "urban", "telecom", "industrial", "health",
    "education", "logistics", "other",
)

# The two halves of the product: what is being built, and what got stopped.
BUILDING_STATUSES = (
    "proposed", "approved", "cleared", "tendered", "awarded",
    "under_construction", "commissioned",
)
BLOCKED_STATUSES = (
    "stalled", "blocked", "rejected", "withdrawn", "cancelled",
)
STATUSES = BUILDING_STATUSES + BLOCKED_STATUSES + ("unknown",)

# Why a project is not moving. Mirrors the "reasons for delay" taxonomy used in
# MoSPI project monitoring reports, plus clearance outcomes from PARIVESH.
BLOCK_REASONS = (
    "land_acquisition", "forest_clearance", "environment_clearance",
    "wildlife_clearance", "litigation", "funds", "contractor",
    "law_and_order", "geological", "utility_shifting", "rehabilitation",
    "tender_failure", "other", "unknown",
)

# How confident are we about where this thing physically is.
GEO_CONFIDENCE = ("exact", "site", "city", "district", "state", "none")
GEO_METHODS = ("source_latlon", "source_geometry", "osm_match", "gazetteer", "manual", "none")


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# --- Record construction -----------------------------------------------------

def blank_record() -> Dict[str, Any]:
    """The full canonical shape, with every field present and null-safe."""
    return {
        "schema_version": SCHEMA_VERSION,
        "id": None,                 # stable synthetic id, see core.ids
        "native_id": None,          # id in the source system, if any
        "title": None,
        "description": None,
        "sector": "other",
        "subsector": None,
        "status": "unknown",
        "status_detail": None,      # verbatim source wording, never normalised away
        "is_blocked": False,        # derived: status in BLOCKED_STATUSES
        "block_reason": None,
        "block_detail": None,

        # Money, always in INR crore for comparability. None if unknown.
        "cost_inr_crore": None,
        "cost_original_inr_crore": None,
        "cost_overrun_pct": None,

        # Time
        "sanctioned_date": None,
        "original_completion_date": None,
        "revised_completion_date": None,
        "commissioned_date": None,
        "delay_months": None,
        "progress_pct": None,

        # Who
        "executing_agency": None,
        "ministry": None,
        "proponent": None,

        # Where
        "geo": {
            "admin": {
                "state": None,
                "district": None,
                "subdistrict": None,
                "lgd_state_code": None,
                "lgd_district_code": None,
            },
            "point": None,          # [lon, lat] GeoJSON order, or None
            "geometry": None,       # GeoJSON geometry (LineString for corridors), or None
            "geo_confidence": "none",
            "geo_method": "none",
            "geo_note": None,
        },

        # Provenance: one entry per source that contributed to this record.
        "provenance": [],

        # Lifecycle
        "first_seen": None,
        "last_seen": None,
        "last_changed": None,
        "tags": [],
    }


def make_provenance(
    source_id: str,
    source_name: str,
    source_url: str,
    retrieved_at: Optional[str] = None,
    fields: Optional[List[str]] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "retrieved_at": retrieved_at or utcnow(),
        "fields": fields or [],
        "note": note,
    }


# --- Derivations -------------------------------------------------------------

def derive(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in fields that are computed from others. Idempotent."""
    rec["is_blocked"] = rec.get("status") in BLOCKED_STATUSES

    orig = rec.get("cost_original_inr_crore")
    cur = rec.get("cost_inr_crore")
    if isinstance(orig, (int, float)) and isinstance(cur, (int, float)) and orig > 0:
        rec["cost_overrun_pct"] = round((cur - orig) / orig * 100.0, 1)

    a, b = rec.get("original_completion_date"), rec.get("revised_completion_date")
    if a and b:
        months = _month_delta(a, b)
        if months is not None:
            rec["delay_months"] = months
    return rec


def _month_delta(a: str, b: str) -> Optional[int]:
    da, db = parse_date(a), parse_date(b)
    if not da or not db:
        return None
    return (db.year - da.year) * 12 + (db.month - da.month)


def parse_date(value: Any) -> Optional[_dt.date]:
    """Tolerant date parsing. Government sources are wildly inconsistent."""
    if not value:
        return None
    if isinstance(value, _dt.date):
        return value
    s = str(value).strip()
    fmts = (
        "%Y-%m-%d", "%Y-%m", "%Y", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
        "%b-%Y", "%B-%Y", "%b %Y", "%B %Y", "%m/%Y", "%d-%b-%Y", "%d-%B-%Y",
    )
    for f in fmts:
        try:
            return _dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def iso_month(value: Any) -> Optional[str]:
    d = parse_date(value)
    return d.isoformat() if d else None


# --- Validation --------------------------------------------------------------

class ValidationError(ValueError):
    pass


REQUIRED = ("id", "title", "sector", "status")


def validate(rec: Dict[str, Any], strict: bool = True) -> List[str]:
    """Return a list of problems. Raises on the fatal ones when strict."""
    problems: List[str] = []

    for f in REQUIRED:
        if not rec.get(f):
            problems.append("missing required field: %s" % f)

    if rec.get("sector") not in SECTORS:
        problems.append("unknown sector: %r" % rec.get("sector"))
    if rec.get("status") not in STATUSES:
        problems.append("unknown status: %r" % rec.get("status"))

    br = rec.get("block_reason")
    if br is not None and br not in BLOCK_REASONS:
        problems.append("unknown block_reason: %r" % br)

    geo = rec.get("geo") or {}
    if geo.get("geo_confidence") not in GEO_CONFIDENCE:
        problems.append("bad geo_confidence: %r" % geo.get("geo_confidence"))
    if geo.get("geo_method") not in GEO_METHODS:
        problems.append("bad geo_method: %r" % geo.get("geo_method"))

    pt = geo.get("point")
    if pt is not None:
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
            problems.append("point must be [lon, lat]")
        else:
            lon, lat = pt
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                problems.append("point out of range: %r" % (pt,))
            # Sanity fence: this is an India tracker. Catches lat/lon swaps,
            # which is the single most common geocoding bug.
            if not (65 <= lon <= 98) or not (5 <= lat <= 38):
                problems.append("point outside India bbox (lat/lon swapped?): %r" % (pt,))

    if not rec.get("provenance"):
        problems.append("no provenance: refusing to publish unsourced records")
    else:
        for p in rec["provenance"]:
            if not p.get("source_url"):
                problems.append("provenance entry without source_url")
            if not p.get("retrieved_at"):
                problems.append("provenance entry without retrieved_at")

    if strict and problems:
        raise ValidationError("%s: %s" % (rec.get("id") or "<no id>", "; ".join(problems)))
    return problems
