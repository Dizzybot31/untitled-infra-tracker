"""Turn Indian place text into coordinates, honestly.

Most government project records have no coordinates at all - just
"4-laning of NH-44 from Km 235 to Km 310 (Telangana)" or "Greenfield airport at
Hollongi, Arunachal Pradesh". This module extracts what it can and, critically,
*labels how good the answer is* so the globe can render uncertainty instead of
pretending to a precision it does not have.

Offline and dependency-free on purpose: no network call, no API key, no rate
limit, reproducible in CI. The tradeoff is coverage, which is why v1 adds an
OSM/Nominatim tier behind a cache (see docs/adr/0004-geocoding.md).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_REF = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ref", "india_places.json")

with open(_REF, "r", encoding="utf-8") as fh:
    _DATA = json.load(fh)

STATES: Dict[str, List[float]] = _DATA["states"]
STATE_ALIASES: Dict[str, str] = _DATA["state_aliases"]
CITIES: Dict[str, List[float]] = _DATA["cities"]
CITY_ALIASES: Dict[str, str] = _DATA["city_aliases"]

# Longest names first so "Andhra Pradesh" wins over a stray "Andhra".
_STATE_KEYS = sorted(list(STATES) + list(STATE_ALIASES), key=len, reverse=True)
_CITY_KEYS = sorted(list(CITIES) + list(CITY_ALIASES), key=len, reverse=True)

# "from Kanpur to Lucknow", "Delhi - Meerut", "Mumbai-Ahmedabad corridor"
_FROM_TO = re.compile(
    r"\bfrom\s+([A-Z][A-Za-z\s]{2,30}?)\s+to\s+([A-Z][A-Za-z\s]{2,30}?)\b",
)
_DASH_PAIR = re.compile(
    r"\b([A-Z][a-z]{3,20})\s*[-–—]\s*([A-Z][a-z]{3,20})\b",
)


def _canon_state(name: str) -> Optional[str]:
    if name in STATES:
        return name
    return STATE_ALIASES.get(name)


def _canon_city(name: str) -> Optional[str]:
    if name in CITIES:
        return name
    return CITY_ALIASES.get(name)


def _find(text: str, keys: List[str]) -> List[str]:
    """Whole-word, case-insensitive scan for any of `keys` in `text`."""
    hits = []
    low = text.lower()
    for k in keys:
        kl = k.lower()
        idx = low.find(kl)
        while idx != -1:
            before_ok = idx == 0 or not low[idx - 1].isalnum()
            after = idx + len(kl)
            after_ok = after >= len(low) or not low[after].isalnum()
            if before_ok and after_ok:
                hits.append(k)
                break
            idx = low.find(kl, idx + 1)
    return hits


def locate(text: str, state_hint: Optional[str] = None, district_hint: Optional[str] = None) -> Dict[str, Any]:
    """Best-effort geocode from free text plus optional structured hints.

    Returns a dict shaped like the canonical record's `geo` block.
    Precedence: explicit hints > city mention > state mention > nothing.
    """
    geo: Dict[str, Any] = {
        "admin": {"state": None, "district": None, "subdistrict": None,
                  "lgd_state_code": None, "lgd_district_code": None},
        "point": None, "geometry": None,
        "geo_confidence": "none", "geo_method": "none", "geo_note": None,
    }
    text = text or ""

    state = _canon_state((state_hint or "").strip()) if state_hint else None
    if not state:
        for hit in _find(text, _STATE_KEYS):
            state = _canon_state(hit)
            if state:
                break
    geo["admin"]["state"] = state
    if district_hint:
        geo["admin"]["district"] = district_hint.strip() or None

    # A named corridor gives us a real LineString, which is the good case:
    # linear projects are what a globe with arcs is actually for.
    endpoints = _corridor(text)
    if endpoints:
        (a_name, a_pt), (b_name, b_pt) = endpoints
        geo["geometry"] = {"type": "LineString", "coordinates": [a_pt, b_pt]}
        geo["point"] = [round((a_pt[0] + b_pt[0]) / 2, 5), round((a_pt[1] + b_pt[1]) / 2, 5)]
        geo["geo_confidence"] = "city"
        geo["geo_method"] = "gazetteer"
        geo["geo_note"] = "corridor endpoints %s - %s from city gazetteer; alignment is a straight line, not the real route" % (a_name, b_name)
        return geo

    cities = [c for c in (_canon_city(h) for h in _find(text, _CITY_KEYS)) if c]
    if cities:
        city = cities[0]
        lat, lon = CITIES[city]
        geo["point"] = [lon, lat]
        geo["geo_confidence"] = "city"
        geo["geo_method"] = "gazetteer"
        geo["geo_note"] = "matched city name %r in title" % city
        if not geo["admin"]["district"]:
            geo["admin"]["district"] = city
        return geo

    if state:
        lat, lon = STATES[state]
        geo["point"] = [lon, lat]
        geo["geo_confidence"] = "state"
        geo["geo_method"] = "gazetteer"
        geo["geo_note"] = "state centroid for %s - project location within the state is unknown" % state
        return geo

    geo["geo_note"] = "no recognisable place name found"
    return geo


def _corridor(text: str) -> Optional[Tuple[Tuple[str, List[float]], Tuple[str, List[float]]]]:
    for rx in (_FROM_TO, _DASH_PAIR):
        for m in rx.finditer(text):
            a, b = m.group(1).strip(), m.group(2).strip()
            ca, cb = _resolve_city_loose(a), _resolve_city_loose(b)
            if ca and cb and ca != cb:
                la, loa = CITIES[ca]
                lb, lob = CITIES[cb]
                return (ca, [loa, la]), (cb, [lob, lb])
    return None


def _resolve_city_loose(name: str) -> Optional[str]:
    name = name.strip().rstrip(",.;:")
    direct = _canon_city(name)
    if direct:
        return direct
    # Try the trailing word: "Greater Noida" -> "Noida"
    parts = name.split()
    for i in range(len(parts)):
        cand = _canon_city(" ".join(parts[i:]))
        if cand:
            return cand
    return None


def coverage_report(records: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        c = ((r.get("geo") or {}).get("geo_confidence")) or "none"
        out[c] = out.get(c, 0) + 1
    return out
