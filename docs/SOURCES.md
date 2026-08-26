# Sources

Every row here was reached and read directly (curl/WebFetch), not inferred from
secondary writeups, on the date shown. Government portals change without
notice; re-verify anything older than a few months before relying on it.

## Live and wired up

### NHAI Data Lake GeoServer — `nhai_geoserver`
**Verified 2026-08-25/26.** `https://datalakew.nhai.gov.in/geoserver/NHAI/ows`
is a standard WFS 2.0 GeoServer with 47 feature layers, no API key, no login,
no rate limiting observed, and no `robots.txt`. Two layers are joined on
`upc` (Unique Project Code):

- `NHAI:adv_upc_wise_alignments_wfs_layers` (1,813 rows) — cost, physical and
  financial progress percentages, contracting status, appointed date,
  scheduled completion date.
- `NHAI:upc_based_allignment_of_nhai_projects` (1,010 rows) — start/end
  coordinates for the alignment. Overlap between the two layers is roughly
  90% by UPC, and only ~95% of those carry non-null coordinates, so real
  geometry coverage is partial, not total (897/1,813 in the last run).

The adapter requests only named columns via WFS `PROPERTYNAME`, not the raw
`MultiLineString` geometry — a full-fidelity pull of the alignment layer is
100+ MB and can take minutes; the layer's own start/end lat-lon columns are
enough to draw the same straight-line corridor the rest of this app already
uses. **Licence: none stated anywhere on the endpoint.** Attribute
prominently, do not bulk-mirror, and see `docs/LEGAL.md`.

Other layers on the same GeoServer, not yet wired up but confirmed live:
`bharatmala_corridors`, `toll_plaza`, `RoadAccident_GIS_Layer`,
`Land_Arbitration_Plot_Layer` (124,621 land parcels — see the privacy note in
LEGAL.md before touching this one), `india_nh`, and per-agency link-project
layers for MoRTH-direct and NHIDCL works.

### Curated seed — `seed`
Hand-entered, not fetched. Exists so the globe is not empty before more
adapters land. Tagged `unverified` and badged in the UI. See
`pipeline/ref/seed_projects.json`.

## Investigated, high-value, not yet wired up

### PAIMANA (MoSPI) — the National Infrastructure Pipeline's replacement
`indiainvestmentgrid.gov.in` (India Investment Grid), which hosted the old
National Infrastructure Pipeline, was **discontinued in 2026** — every route
now serves a static notice pointing to PAIMANA. PAIMANA
(`paimana-proj.mospi.gov.in`) exposes an **undocumented, unauthenticated JSON
endpoint**, `POST /Home/GetTileData`, that has been observed to return the
entire project register (1,775 rows, ~1.25 MB) in one call with no cookie, no
session, no CSRF token — and has *also* been observed to fail with an HTTP 500
`maxJsonLength` serialization error on the exact same call. **Treat it as
flaky, not dead**: the working mitigation found is to query per-state
(`StateId=<n>` for each of ~36 populated state ids), which keeps each response
small enough to avoid the bug. Fields are rich (26 columns: cost, revised
cost, original/revised completion date, physical progress) but `StateName`,
`RevisedDateReason`, `RevisedCostReason`, and `Remarks` are **null in every
record** — the delay-reason narrative the old OCMS reports were valued for is
not in this payload; it survives only in the monthly PDF flash reports
(archive back to April 2015, 131 reports, real text layer, layout-aware
extraction needed). No lat/lon at national level, at all, in any field.
**Licence: none stated**, plus a hyperlink policy demanding prior permission
to link to the site at all — the biggest open legal question in this project.
Recommended before shipping this adapter: build it with the per-state
workaround, and email MoSPI's IPMD for written clearance.

### data.gov.in
A genuinely documented, keyed REST API (`api.data.gov.in`) under the
Government Open Data Licence – India (GODL), free registration. But its
`&query=` parameter is silently ignored (confirmed: three different queries
returned byte-identical results), there is no national infrastructure-pipeline
catalog on it, and its sector filter for "Infrastructure" returns 21 municipal
trivia datasets. The HTML site itself (`data.gov.in/robots.txt`) disallows all
crawling — API only, never scrape the web UI.

### MoRTH direct sources
`epace.nic.in` (the MoRTH Project Monitoring System commonly cited in older
writeups) is `NXDOMAIN` — gone. `dashboard.morth.gov.in` resolves but refused
every connection tested from outside India; it may be geo-fenced to Indian
network ranges and needs an India-based check before anyone relies on a
description of its contents.

### Railways
The central Railway Board "Pink Book" (Works, Machinery & Rolling Stock
Programme) was **discontinued as a single publication after FY2024-25** — from
FY2025-26 each of ~17 zonal railways publishes its own PDF separately, with
inconsistent formatting. PDFs have a real text layer (not scanned) but need
layout-aware extraction (pdfplumber/camelot); expect image-only cover pages.
No stable cross-year project identifier exists for railways the way NHAI's UPC
does for roads — expect fuzzy name+zone matching. The best cross-sector
fallback for both roads and rail is MoSPI's own monthly Flash Report on
Central Sector Projects (₹150 crore+), which does carry structured cost and
time overrun per project.

### Investigated and ruled out
- **PRAGATI** (`pragati.nic.in`) — login-only, with active bot-fingerprinting
  (FingerprintJS cookies). Do not attempt automated access.
- **NDAP** (NITI Aayog) — pure React SPA; every plausible API path 404s to the
  shell; the only backend host found in its JS bundle is a QA host. No
  infrastructure-pipeline data even if a real API were found.
- **PM Gati Shakti** — root domain 404s; the "public" geospatial layer
  referenced in press coverage could not be reached at any of four guessed
  hostnames. Low confidence; needs a browser session to confirm it exists.

## The freshness table

| Tier | Real update cadence | Achievable pipeline latency |
|---|---|---|
| NHAI GeoServer progress fields | NHAI's internal MIS cycle, believed monthly | Same day as query, whenever cron runs |
| PAIMANA JSON (if stabilised) | Monthly "freeze" | Same day, once per freeze detected |
| MoSPI Flash Report PDF | Monthly | A few days after publication |
| Zonal Railway Pink Books | Annual | Once a year, per zone |
| PARIVESH clearance register | Rolling, per proposal | Not yet adapter-verified — see open work |

Nothing here is real-time in the sense of "seconds behind the source." The
honest, defensible claim is: **updated on a schedule, every number dated and
sourced.**
