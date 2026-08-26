"""NHAI's public GeoServer - the strongest real source found for this project.

https://datalakew.nhai.gov.in/geoserver/NHAI/ows serves 47 WFS layers with no
API key, no login, and no rate limiting observed. Verified live 2026-08-25/26.
This adapter joins two of them:

  * adv_upc_wise_alignments_wfs_layers  - cost, physical/financial progress,
    status, appointed/scheduled-completion dates. ~1,813 rows. This is the
    primary record: everything a project row needs except a location.
  * upc_based_allignment_of_nhai_projects - the alignment geometry, keyed by
    the same `upc` (Unique Project Code). Only ~90% of UPCs overlap between
    the two layers, and only ~95% of alignment rows carry non-null start/end
    coordinates - so geometry coverage here is real but partial, not total.

Only lightweight columns are requested via WFS `PROPERTYNAME`, not the raw
MultiLineString geometry: a full-fidelity pull of the alignment layer is
100+ MB and single-digit-minutes even on a good connection, which is a bad fit
for a file committed to git on every scheduled run. We take the layer's own
start/end lat-lon columns instead and draw a straight corridor between them -
exactly the same "endpoints, not a real alignment" model already used
elsewhere in this pipeline, so the frontend needs no special case for it.

Do not point this adapter at datalakeg.nhai.gov.in (the dashboard front end):
it is server-rendered HTML with no export and no inline data; the GeoServer
above is where the dashboard's own map code actually reads from.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ..core import schema
from .base import Adapter, SchemaDrift, SourceUnavailable

BASE = "https://datalakew.nhai.gov.in/geoserver/NHAI/ows"

PROGRESS_LAYER = "NHAI:adv_upc_wise_alignments_wfs_layers"
PROGRESS_FIELDS = (
    "upc,adv_project_name,adv_total_capital_cost,"
    "adv_cumphysical_progress_tilllastmonth,adv_cumfinancial_progress_tilllastmonth,"
    "adv_appointed_date,adv_scheduled_completion_date,district_name,current_st,"
    "state,nh_new,adv_length,adv_mode,adv_lanes,green_brown_field"
)

ALIGNMENT_LAYER = "NHAI:upc_based_allignment_of_nhai_projects"
ALIGNMENT_FIELDS = (
    "upc,project_na,current_st,state,nh__new_,length,lane,scheme,mode,"
    "starting_l,starting_1,end_latitu,end_longit,phase"
)

# current_st is NHAI's own contracting-lifecycle vocabulary (AD = Appointed
# Date, PCC/CC = Provisional/final Completion Certificate, O&M = operations
# and maintenance). Mapped conservatively into the canonical vocabulary;
# the verbatim value always survives in status_detail regardless.
STATUS_MAP = {
    "Balance for Award": "tendered",
    "Awarded, Not Appointed": "awarded",
    "Under Construction (AD issued)": "under_construction",
    "PCC Issued, CC Pending": "under_construction",
    "CC Issued & O&M by Construction Agency": "commissioned",
    "Under O&M through OMT/TOT/O&M Agency at Site": "commissioned",
    "Completed & Agency Demobilised (Civil/O&M)": "commissioned",
    "O&M on Project no more required": "commissioned",
    "Terminated": "cancelled",
}


def _wfs_json(fetch_fn, layer: str, properties: str) -> Dict[str, Any]:
    url = (
        "%s?service=WFS&version=2.0.0&request=GetFeature&typeName=%s"
        "&outputFormat=application/json&propertyName=%s" % (BASE, layer, properties)
    )
    res = fetch_fn(url, delay=3.0, timeout=60)
    if not res.ok:
        raise SourceUnavailable("%s: %s (%s)" % (layer, res.outcome, res.note))
    try:
        data = res.json()
    except ValueError as e:
        raise SchemaDrift("%s did not return JSON: %s" % (layer, e))
    if "features" not in data:
        raise SchemaDrift("%s response has no 'features' key - GeoServer shape changed" % layer)
    return data


class NhaiGeoserverAdapter(Adapter):
    source_id = "nhai_geoserver"
    source_name = "NHAI Data Lake GeoServer"
    source_url = "https://datalakew.nhai.gov.in/geoserver/NHAI/ows"
    publisher = "National Highways Authority of India"
    upstream_cadence = "monthly (physical/financial progress fields update on NHAI's internal MIS cycle)"
    access_mode = "api"
    licence = "unknown - no licence or terms stated on the endpoint; attribute prominently, do not bulk-mirror"

    def fetch(self) -> Any:
        from ..core.fetch import fetch as http_fetch
        progress = _wfs_json(http_fetch, PROGRESS_LAYER, PROGRESS_FIELDS)
        alignment = _wfs_json(http_fetch, ALIGNMENT_LAYER, ALIGNMENT_FIELDS)
        return {"progress": progress, "alignment": alignment}

    def parse(self, raw: Any) -> Iterable[Dict[str, Any]]:
        align_by_upc: Dict[str, Dict[str, Any]] = {}
        for f in raw["alignment"]["features"]:
            p = f["properties"]
            upc = p.get("upc")
            if upc:
                align_by_upc[upc] = p

        retrieved_at = schema.utcnow()
        seen_upcs = set()

        for f in raw["progress"]["features"]:
            p = f["properties"]
            upc = p.get("upc")
            title = p.get("adv_project_name")
            if not upc or not title:
                continue  # a handful of rows are placeholders; skip rather than fabricate an id
            seen_upcs.add(upc)

            rec = self.new_record(upc, title, retrieved_at=retrieved_at,
                                  page_url="https://datalakew.nhai.gov.in/geoserver/NHAI/ows?"
                                           "service=WFS&request=GetFeature&typeName=%s"
                                           "&CQL_FILTER=upc=%%27%s%%27&outputFormat=application/json"
                                           % (PROGRESS_LAYER, upc))
            rec["sector"] = "road"
            rec["subsector"] = p.get("green_brown_field")

            raw_status = p.get("current_st")
            rec["status"] = STATUS_MAP.get(raw_status, "unknown")
            rec["status_detail"] = raw_status
            if rec["status"] == "cancelled":
                rec["block_reason"] = "other"
                rec["block_detail"] = (
                    "NHAI records this contract's status as 'Terminated'. The public "
                    "GeoServer layer does not state a termination reason."
                )

            cost = _num(p.get("adv_total_capital_cost"))
            rec["cost_inr_crore"] = cost

            progress_pct = _num(p.get("adv_cumphysical_progress_tilllastmonth"))
            # NHAI stops updating this field once a contract closes out, so a
            # completed project shows 0.00 - which would read as "not started"
            # if published as-is. Suppress the number in that specific case;
            # the status field already communicates completion.
            if progress_pct == 0 and rec["status"] == "commissioned":
                progress_pct = None
            rec["progress_pct"] = progress_pct

            rec["revised_completion_date"] = schema.iso_month(p.get("adv_scheduled_completion_date"))
            appointed = p.get("adv_appointed_date")
            if appointed:
                note = "Construction appointed date (contractor start): %s." % appointed
                rec["status_detail"] = ("%s %s" % (rec["status_detail"] or "", note)).strip()

            district = (p.get("district_name") or "").split("|")[0].strip() or None
            state = p.get("state")
            rec["executing_agency"] = "National Highways Authority of India"
            rec["ministry"] = "Ministry of Road Transport and Highways"

            align = align_by_upc.get(upc)
            geo = _geometry_for(align, title, state, district)
            rec["geo"] = geo

            rec["tags"] = ["nhai", "road"]
            if align is None:
                rec["tags"].append("no_alignment_match")
            yield schema.derive(rec)


def _geometry_for(align: Optional[Dict[str, Any]], title: str, state: Optional[str],
                  district: Optional[str]) -> Dict[str, Any]:
    if align:
        lat1, lon1 = align.get("starting_l"), align.get("starting_1")
        lat2, lon2 = align.get("end_latitu"), align.get("end_longit")
        if _valid_latlon(lat1, lon1) and _valid_latlon(lat2, lon2):
            same = abs(lat1 - lat2) < 1e-6 and abs(lon1 - lon2) < 1e-6
            geo = {
                "admin": {"state": state, "district": district,
                          "subdistrict": None, "lgd_state_code": None, "lgd_district_code": None},
                "point": [round((lon1 + lon2) / 2, 6), round((lat1 + lat2) / 2, 6)],
                "geometry": None if same else {
                    "type": "LineString",
                    "coordinates": [[round(lon1, 6), round(lat1, 6)], [round(lon2, 6), round(lat2, 6)]],
                },
                "geo_confidence": "site",
                "geo_method": "source_latlon",
                "geo_note": "Start/end coordinates as published by NHAI for this alignment; "
                            "the line drawn is straight between them, not the true road geometry.",
            }
            return geo
        if _valid_latlon(lat1, lon1):
            return {
                "admin": {"state": state, "district": district,
                          "subdistrict": None, "lgd_state_code": None, "lgd_district_code": None},
                "point": [round(lon1, 6), round(lat1, 6)],
                "geometry": None,
                "geo_confidence": "site",
                "geo_method": "source_latlon",
                "geo_note": "Only a start coordinate was published for this alignment.",
            }

    from ..core import gazetteer
    geo = gazetteer.locate(title, state_hint=state, district_hint=district)
    if geo["point"] is not None:
        geo["geo_note"] = (geo["geo_note"] or "") + " (NHAI published no coordinates for this UPC.)"
    return geo


def _valid_latlon(lat: Any, lon: Any) -> bool:
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    return 5 <= lat <= 38 and 65 <= lon <= 98


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        n = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return n if n == n else None  # filter NaN
