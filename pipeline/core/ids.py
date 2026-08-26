"""Stable identity and entity resolution.

Two separate problems, often conflated:

  1. *Stable ids* - the same row from the same source must get the same id on
     every run, or change detection is meaningless and the frontend loses
     selection state. Solved by hashing (source_id, native_id or title).

  2. *Entity resolution* - the Navi Mumbai airport appears in a MoSPI project
     report, in a PARIVESH clearance record, and in a tender award, under three
     different names. Linking those is the hard part and is deliberately
     conservative here: we only merge on strong evidence, and we record why.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")

# Words that carry no discriminating power in Indian infra project titles.
STOPWORDS = {
    "the", "of", "and", "for", "to", "from", "in", "at", "on", "by", "with",
    "project", "projects", "work", "works", "construction", "constn",
    "development", "upgradation", "upgrade", "improvement", "package", "pkg",
    "phase", "ph", "section", "sec", "stretch", "km", "kms", "including",
    "incl", "etc", "new", "existing", "proposed", "scheme", "nh", "sh",
}


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = _PUNCT.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


def record_id(source_id: str, native_id: Optional[str], title: Optional[str]) -> str:
    """Deterministic id. Prefers the source's own key; falls back to the title."""
    key = native_id if native_id else slugify(title or "")
    if not key:
        raise ValueError("cannot build an id without native_id or title")
    h = hashlib.sha1(("%s|%s" % (source_id, key)).encode("utf-8")).hexdigest()[:16]
    return "%s-%s" % (source_id, h)


def title_tokens(title: str) -> List[str]:
    return [t for t in slugify(title).split() if t and t not in STOPWORDS and len(t) > 2]


def title_fingerprint(title: str) -> str:
    """Order-insensitive fingerprint, for cheap blocking before pair scoring."""
    toks = sorted(set(title_tokens(title)))
    return hashlib.sha1(" ".join(toks).encode("utf-8")).hexdigest()[:12]


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def haversine_km(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """p1/p2 are [lon, lat]."""
    from math import asin, cos, radians, sin, sqrt
    lon1, lat1 = radians(p1[0]), radians(p1[1])
    lon2, lat2 = radians(p2[0]), radians(p2[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


# --- Match scoring -----------------------------------------------------------

MERGE_THRESHOLD = 0.72       # link and merge
REVIEW_THRESHOLD = 0.55      # surface for human review, do not auto-merge


def match_score(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Score two canonical records as the same real-world project.

    Returns (score, reasons). Conservative by design: name similarity alone
    never clears MERGE_THRESHOLD without at least one corroborating signal.
    """
    reasons: List[str] = []
    name = jaccard(title_tokens(a.get("title") or ""), title_tokens(b.get("title") or ""))
    score = 0.55 * name
    if name > 0.5:
        reasons.append("title overlap %.2f" % name)

    # Same state is weak; same district is decent.
    ga = (a.get("geo") or {}).get("admin") or {}
    gb = (b.get("geo") or {}).get("admin") or {}
    if ga.get("state") and ga.get("state") == gb.get("state"):
        score += 0.10
        reasons.append("same state")
        if ga.get("district") and ga.get("district") == gb.get("district"):
            score += 0.10
            reasons.append("same district")

    # Physical proximity, only meaningful if both are better than state-level.
    pa = (a.get("geo") or {}).get("point")
    pb = (b.get("geo") or {}).get("point")
    ca = (a.get("geo") or {}).get("geo_confidence")
    cb = (b.get("geo") or {}).get("geo_confidence")
    if pa and pb and ca in ("exact", "site", "city") and cb in ("exact", "site", "city"):
        d = haversine_km(pa, pb)
        if d < 5:
            score += 0.15
            reasons.append("within %.1f km" % d)
        elif d > 150:
            score -= 0.30
            reasons.append("%.0f km apart - probably different projects" % d)

    if a.get("sector") == b.get("sector") and a.get("sector") != "other":
        score += 0.05
        reasons.append("same sector")
    elif a.get("sector") != b.get("sector"):
        score -= 0.15
        reasons.append("different sector")

    # Cost agreement within 20% is a strong corroborator.
    ka, kb = a.get("cost_inr_crore"), b.get("cost_inr_crore")
    if isinstance(ka, (int, float)) and isinstance(kb, (int, float)) and max(ka, kb) > 0:
        ratio = min(ka, kb) / float(max(ka, kb))
        if ratio > 0.8:
            score += 0.10
            reasons.append("cost within 20%")

    return max(0.0, min(1.0, score)), reasons


def find_links(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Cross-source candidate links. Blocks on shared tokens to stay O(n*k).

    Returns {"merge": [...], "review": [...]} of {a, b, score, reasons}.
    Never merges two records from the same source: within one source, the
    source's own key is authoritative.
    """
    by_token: Dict[str, List[int]] = {}
    for i, r in enumerate(records):
        for t in set(title_tokens(r.get("title") or "")):
            by_token.setdefault(t, []).append(i)

    seen_pairs = set()
    out: Dict[str, List[Dict[str, Any]]] = {"merge": [], "review": []}
    for token, idxs in by_token.items():
        if len(idxs) > 200:      # a token this common is not discriminating
            continue
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                i, j = idxs[x], idxs[y]
                key = (min(i, j), max(i, j))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                a, b = records[i], records[j]
                if _source_of(a) == _source_of(b):
                    continue
                score, reasons = match_score(a, b)
                if score >= MERGE_THRESHOLD:
                    out["merge"].append({"a": a["id"], "b": b["id"], "score": round(score, 3), "reasons": reasons})
                elif score >= REVIEW_THRESHOLD:
                    out["review"].append({"a": a["id"], "b": b["id"], "score": round(score, 3), "reasons": reasons})
    return out


def _source_of(rec: Dict[str, Any]) -> Optional[str]:
    prov = rec.get("provenance") or []
    return prov[0].get("source_id") if prov else None
