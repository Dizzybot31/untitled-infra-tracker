"""PAIMANA - MoSPI's central project monitoring register.

This is the second networked source, and it does something NHAI cannot: it
publishes an ORIGINAL target completion date for every project it carries. That
is what makes "this was meant to finish in 2021, the source now says 2027"
sayable at all.

SCOPE IS DELIBERATELY NARROW: Railways only (SectorId 108, ~192 rows).

The register also carries 993 "Roads & Highways" rows, and those are NOT
ingested. They are largely the same contracts NHAI already gives us under a
slightly different spelling - 489 of them match an existing NHAI title once
punctuation is stripped, corroborated by cost agreeing within 2% on 489/489 and
completion dates agreeing to the month on 489/489. Ingesting them naively would
insert roughly 489 duplicate national highways: some as visible twin dots, the
rest as phantom store rows that publish.py drops, leaving the census arithmetic
silently wrong. Railways has ZERO overlap with the existing corpus, which is why
it goes first. The join spec for roads is written up in docs/SOURCES.md.

TRAPS, all measured rather than assumed:
  * Always send Month, Year AND MonthYear. A missing or unparseable MonthYear
    returns a deterministic HTTP 500 "maxJsonLength" serialization error. A 500
    here means OUR request was malformed - do not retry it.
  * Never read data.isLive or data.ProjectCount. Both report False/0 on a
    perfectly good 192-row response.
  * Per-state queries assign state; they never source rows. Summed over the 36
    states they return 250 rows for 192 projects, because 54 projects are
    registered under two or more states. Using them as a row source would
    double-count by 30%.
  * The lookup endpoints (GetStateList/GetSectorList) have a reproducible ~23s
    server-side stall, so their values are committed as reference data instead.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..core import gazetteer, schema
from .base import Adapter, SchemaDrift, SourceUnavailable

BASE = "https://paimana-proj.mospi.gov.in"
TILE_URL = BASE + "/Home/GetTileData"
FREEZE_URL = BASE + "/Home/GetFreezeDates"

RAILWAYS_SECTOR_ID = 108

_REF = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ref")
_STATE_IDS = os.path.join(_REF, "paimana_state_ids.json")
_ASSIGNMENT = os.path.join(_REF, "paimana_state_assignment.json")

# The exact field set as of the 2026-07 freeze. Any change is schema drift: this
# is an undocumented internal endpoint on a portal rebuilt twice in a year.
EXPECTED_FIELDS = frozenset({
    "AgencyId", "AgencyName", "COMPANYNAME", "COR_PERC", "COST_OVERRUN",
    "COST_OVERRUN_PERC", "CreationDate", "DELAYED_TIME", "Expenditure",
    "LineMinistry", "OnboardingDelay", "OriginalCost", "OriginalEndDate",
    "PhysicalProgress", "ProjectId", "ProjectName", "Remarks", "RevisedCost",
    "RevisedCostReason", "RevisedDate", "RevisedDateReason", "SanctionDate", "SectorName",
    "StartDate", "StateName", "TOR_PERC",
})

# Populated on every row but with no canonical home, and deliberately not mapped:
# "spent to date against sanction" would be a second new capability.
_IGNORED_ALWAYS_ZERO = ("DELAYED_TIME", "COST_OVERRUN", "COST_OVERRUN_PERC",
                        "COR_PERC", "TOR_PERC", "OnboardingDelay")


def _load_state_ids() -> Dict[str, str]:
    with open(_STATE_IDS, "r", encoding="utf-8") as fh:
        return json.load(fh)["states"]


class MospiPaimanaAdapter(Adapter):
    source_id = "mospi_paimana"
    source_name = "PAIMANA - Infrastructure & Project Monitoring Division, MoSPI"
    source_url = BASE + "/"
    publisher = "Ministry of Statistics and Programme Implementation, Government of India"
    upstream_cadence = (
        "monthly freeze, published in arrears; the latest frozen month is announced by "
        "/Home/GetFreezeDates. Rolling 13-month window - older months drop off."
    )
    access_mode = "api"
    licence = (
        "unknown - no licence or terms of use are published anywhere on the site. It asserts "
        "'Copyright (c) 2025 Ministry of Statistics and Programme Implementation' and a hyperlink "
        "policy requesting prior permission to link. Attribute prominently, link only to the "
        "portal landing page, do not bulk-mirror."
    )

    # -- fetch ---------------------------------------------------------------

    def fetch(self) -> Any:
        from ..core.fetch import fetch as http_fetch

        freeze = _freeze_month(http_fetch)
        payload = _post_tile(http_fetch, freeze, RAILWAYS_SECTOR_ID)
        rows = _health_check(payload, freeze)
        states = _state_assignment(http_fetch, freeze, [str(r["ProjectId"]) for r in rows])
        return {"freeze": freeze, "rows": rows, "states": states}

    # -- parse ---------------------------------------------------------------

    def parse(self, raw: Any) -> Iterable[Dict[str, Any]]:
        freeze = raw["freeze"]
        states_by_id = raw["states"]
        retrieved_at = schema.utcnow()
        freeze_date = schema.parse_date(freeze + "-01")

        for row in raw["rows"]:
            native_id = str(row.get("ProjectId") or "").strip()
            title = (row.get("ProjectName") or "").strip()
            if not native_id or native_id == "0":
                # ids.record_id() would silently fall back to slugify(title), and
                # this source rewrites ~9% of titles per month - that would mint a
                # new record on every rename and destroy the project's history.
                raise SchemaDrift("PAIMANA row has no usable ProjectId: %r" % (row,))
            if not title:
                continue

            rec = self.new_record(native_id, title, retrieved_at=retrieved_at,
                                  page_url=self.source_url)
            rec["sector"] = "rail"
            rec["subsector"] = row.get("SectorName")
            rec["ministry"] = row.get("LineMinistry")

            agency = (row.get("COMPANYNAME") or "").strip()
            rec["executing_agency"] = None if agency.upper() == "INVALID CO." else (agency or None)

            original_cost = _num(row.get("OriginalCost"))
            revised_cost = _num(row.get("RevisedCost"))
            rec["cost_original_inr_crore"] = original_cost
            rec["cost_inr_crore"] = revised_cost if revised_cost is not None else original_cost

            rec["sanctioned_date"] = schema.iso_month(row.get("SanctionDate"))
            original_end = schema.iso_month(row.get("OriginalEndDate"))
            revised = schema.iso_month(row.get("RevisedDate"))
            rec["original_completion_date"] = original_end

            tags = ["paimana", "rail"]

            if revised:
                rec["revised_completion_date"] = revised
            else:
                # bucketOf() in the frontend reads only revised_completion_date, so
                # leaving it null would bucket these as "no date published" when a
                # date is in fact published. But copying the original across makes
                # derive() compute delay_months = 0, which renders as "no slip"
                # when the truth is "no revision published". Set the fallback, then
                # explicitly clear the derived slip below.
                rec["revised_completion_date"] = original_end
                tags.append("no_revised_date")

            rec["progress_pct"] = _num(row.get("PhysicalProgress"))

            status, detail = _status_for(row, freeze_date)
            rec["status"] = status
            rec["status_detail"] = detail
            # This source publishes no obstruction information at all:
            # RevisedDateReason and RevisedCostReason are null on every row.
            rec["is_blocked"] = False
            rec["block_reason"] = None

            assigned = states_by_id.get(native_id) or []
            for st in assigned:
                tags.append("state:" + st)
            if len(assigned) > 1:
                tags.append("multi_state")
            elif not assigned:
                tags.append("no_state")

            rec["geo"] = _geo_for(title, assigned)

            rec["provenance"][0]["note"] = (
                "MoSPI project monitoring register, as frozen for %s. This source publishes one "
                "monthly snapshot in arrears and no per-project page, so the link is to the "
                "portal itself." % freeze
            )

            schema.derive(rec)

            # Applied AFTER derive(), which would otherwise report a fabricated
            # zero slip for rows whose revised date is only a fallback.
            if "no_revised_date" in tags:
                rec["delay_months"] = None
            if original_end and revised and rec.get("delay_months") is None and revised < original_end:
                tags.append("revised_earlier_than_original")

            # Same rule as the inverted dates, applied to cost. A "revised" cost
            # under half the original is the source disagreeing with itself, not a
            # 90% saving - Hubli-Ankola reports 5,174 crore sanctioned against a
            # 533 crore revision while 10% built. 2 of 192 railway rows do this.
            # Show both figures, compute no percentage.
            if (original_cost and revised_cost is not None
                    and revised_cost < original_cost * 0.5):
                rec["cost_overrun_pct"] = None
                tags.append("cost_figures_inconsistent")

            rec["tags"] = tags
            yield rec


# --- fetch helpers ----------------------------------------------------------

def _freeze_month(http_fetch) -> str:
    res = http_fetch(FREEZE_URL, delay=2.0, timeout=60, use_cache=False)
    if not res.ok:
        raise SourceUnavailable("GetFreezeDates: %s (%s)" % (res.outcome, res.note))
    try:
        data = res.json()
    except ValueError as e:
        raise SchemaDrift("GetFreezeDates did not return JSON: %s" % e)
    freeze = data.get("lastFreeze")
    if not freeze:
        raise SchemaDrift("GetFreezeDates has no lastFreeze: %r" % (data,))
    return freeze


def _post_tile(http_fetch, freeze: str, sector_id: int,
               state_id: Optional[int] = None) -> Dict[str, Any]:
    year, month = freeze.split("-")
    fields = {
        # All three are mandatory. Omitting MonthYear reproducibly returns an
        # HTTP 500 maxJsonLength serialization error.
        "Month": str(int(month)),
        "Year": year,
        "MonthYear": freeze,
        "SectorId": str(sector_id),
    }
    if state_id is not None:
        fields["StateId"] = str(state_id)
    body = urllib.parse.urlencode(fields).encode("ascii")

    res = http_fetch(TILE_URL, delay=2.0, timeout=120, use_cache=False, data=body,
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    if not res.ok:
        if res.status == 500:
            raise SourceUnavailable(
                "GetTileData returned HTTP 500. On this endpoint that means the REQUEST was "
                "malformed (usually a missing or unparseable MonthYear), not a transient "
                "server fault. Do not retry without checking the parameters. Sent: %r" % fields)
        raise SourceUnavailable("GetTileData: %s (%s)" % (res.outcome, res.note))
    try:
        return res.json()
    except ValueError as e:
        raise SchemaDrift("GetTileData did not return JSON: %s" % e)


def _health_check(payload: Dict[str, Any], freeze: str) -> List[Dict[str, Any]]:
    """Validate hard. This is an undocumented endpoint that can change silently."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SchemaDrift("GetTileData response has no 'data' object")

    rows = data.get("ProjectsCountTabDetails")
    if not isinstance(rows, list):
        raise SchemaDrift("GetTileData has no ProjectsCountTabDetails array")

    # The row count the server reports for itself, which is the only reliable
    # self-consistency signal on this payload.
    try:
        declared = int(data["totalProjectsTabData"][0]["TotalProject"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise SchemaDrift("GetTileData has no totalProjectsTabData[0].TotalProject")

    if len(rows) != declared:
        raise SchemaDrift("row count mismatch: %d rows returned, %d declared"
                          % (len(rows), declared))

    # We only ever ask for lastFreeze, so the month IS published. Zero rows means
    # the source broke, and exiting quietly here would let the site go stale.
    if declared == 0:
        raise SchemaDrift("published freeze %s returned zero railway rows" % freeze)

    got = set(rows[0].keys())
    if got != EXPECTED_FIELDS:
        raise SchemaDrift("field set changed. missing=%s unexpected=%s"
                          % (sorted(EXPECTED_FIELDS - got), sorted(got - EXPECTED_FIELDS)))

    off = {r.get("SectorName") for r in rows} - {"Railways"}
    if off:
        raise SchemaDrift("SectorId=%d returned non-railway sectors: %s"
                          % (RAILWAYS_SECTOR_ID, sorted(off)))
    return rows


def _state_assignment(http_fetch, freeze: str, project_ids: List[str]) -> Dict[str, List[str]]:
    """ProjectId -> canonical state names.

    StateName is null on every row, so state is recovered by asking which states
    a project appears under. This is a MANY-TO-MANY assignment, not a partition:
    54 of 192 projects appear under two or more states, and the per-state counts
    sum to 250. These calls assign state; they never source rows.

    Cached to disk and only rebuilt when the freeze month advances or an unseen
    project appears, so a normal run makes two requests, not thirty-eight.
    """
    cached = {}
    if os.path.exists(_ASSIGNMENT):
        try:
            with open(_ASSIGNMENT, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
        except ValueError:
            cached = {}

    known = cached.get("assignment") or {}
    if cached.get("freeze") == freeze and all(pid in known for pid in project_ids):
        return known

    state_ids = _load_state_ids()
    assignment: Dict[str, List[str]] = {}
    for sid, name in sorted(state_ids.items(), key=lambda kv: int(kv[0])):
        payload = _post_tile(http_fetch, freeze, RAILWAYS_SECTOR_ID, state_id=int(sid))
        rows = (payload.get("data") or {}).get("ProjectsCountTabDetails") or []
        for r in rows:
            pid = str(r.get("ProjectId") or "")
            if pid:
                assignment.setdefault(pid, [])
                if name not in assignment[pid]:
                    assignment[pid].append(name)

    with open(_ASSIGNMENT, "w", encoding="utf-8") as fh:
        json.dump({
            "_note": ("ProjectId -> states the project is registered under, recovered by querying "
                      "each StateId because StateName is null on every row. Many-to-many: the "
                      "per-state counts sum to more than the project count. Rebuilt only when the "
                      "freeze month advances or an unseen project appears."),
            "freeze": freeze,
            "assignment": assignment,
        }, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return assignment


# --- derivation helpers -----------------------------------------------------

def _status_for(row: Dict[str, Any], freeze_date) -> Tuple[str, Optional[str]]:
    """PAIMANA publishes no status field, only dates, cost and progress."""
    progress = _num(row.get("PhysicalProgress")) or 0.0
    spend = _num(row.get("Expenditure")) or 0.0
    end = schema.parse_date(row.get("RevisedDate") or row.get("OriginalEndDate"))

    if progress >= 100:
        if end and freeze_date and end <= freeze_date:
            return "commissioned", None
        return "under_construction", (
            "Physical progress is reported as 100%%, but the completion date this source "
            "publishes (%s) has not yet been reached." % (row.get("RevisedDate")
                                                          or row.get("OriginalEndDate")))
    if progress > 0:
        return "under_construction", None
    if spend > 0:
        return "under_construction", (
            "No physical progress is reported. Expenditure of %s crore has been recorded "
            "against this project." % spend)
    if row.get("SanctionDate"):
        return "approved", None
    return "unknown", None


def _geo_for(title: str, assigned: List[str]) -> Dict[str, Any]:
    """One state -> use it as a hint. Two or more -> no state centroid.

    Placing a corridor that crosses several states on one state's dot asserts
    something the source does not say. Those records are published as explicitly
    unlocated instead.
    """
    if len(assigned) == 1:
        return gazetteer.locate(title, state_hint=assigned[0])
    return gazetteer.locate(title)


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        n = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return n if n == n else None
