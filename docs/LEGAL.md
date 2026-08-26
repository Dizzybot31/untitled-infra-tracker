# Legal and licensing notes

This file exists so decisions here are deliberate, not accidental. It is not
legal advice; get real legal review before this handles meaningful traffic.

## Licensing, per source

- **GODL-India** (data.gov.in datasets) is genuinely permissive: worldwide,
  royalty-free licence to use, adapt, publish, and create derivative works,
  including commercial products, gazetted under NDSAP-2012. Conditions that
  must actually be implemented, not just acknowledged: (a) attribution in the
  prescribed format, per dataset, not one blanket credit line; (b)
  non-endorsement — nothing may imply the data provider endorses this project.
- **NHAI GeoServer, MoSPI Flash Reports, PAIMANA, Pink Book PDFs**: **no
  licence or terms stated anywhere on the endpoints or files.** Indian
  government works default to Crown-copyright-style protection; public
  reachability is not the same as an open licence. Until this is resolved:
  attribute prominently and link back to the source on every record, do not
  bulk-mirror raw dumps as if they were this project's own data, and treat any
  wholesale republication as a legally grey area pending confirmation.
- **PAIMANA specifically** carries a "Hyperlink Policy" that asks for prior
  permission before linking to the site at all. Practical stance taken here:
  linking directly to a specific record's data (as provenance, which is the
  whole point of this project) is treated as fair use of a public record; a
  prominent front-page link farm to the portal is not attempted. Get written
  confirmation from MoSPI's IPMD before this adapter goes into wide use.

## Personal data

- The NHAI `Land_Arbitration_Plot_Layer` (124,621 land parcels) carries an
  `owner_ship` field — individual landowners' names on acquired parcels. **Do
  not ingest or publish this layer at parcel/owner granularity.** If it is
  used at all, aggregate to district or project level first and drop the
  ownership field entirely.
- Any future PARIVESH adapter will encounter proponent contact names on
  clearance applications. Same rule: publish the organisation, not an
  individual's personal contact details, unless the source itself already
  treats that as public-facing (e.g. a company director listed in a public
  filing).
- This is a DPDP Act 2023 concern, not just good manners. When in doubt, drop
  the field.

## "Investment insight" and SEBI

This project visualises public project status and cost data. It does **not**
recommend buying, selling, or holding any security, and does not target
specific listed companies' shares. To stay clearly outside SEBI's Investment
Adviser / Research Analyst regulations:

- Never phrase anything as "buy," "sell," "undervalued," or "a good bet" —
  show facts (cost, delay, status) and let the reader draw conclusions.
- Never attach a specific stock ticker or "invest in X" suggestion to a
  project record.
- Keep the disclaimer (already baked into `meta.json` and the footer) visible
  wherever the data is shown, not buried in a separate page.
- If a "which regions have the most active investment" feature is ever built,
  frame it as regional infrastructure activity, not a stock or asset
  recommendation.

## Defamation / accuracy risk

Labelling a project "stalled," "rejected," or naming a contractor as delayed
carries real risk if the underlying government data is stale or simply wrong.
Mitigations already built into the schema, not optional:

- Every record shows its exact source URL and retrieval timestamp — the UI
  says "as reported by X on date Y," not "this is true."
- The original source's own wording is always preserved verbatim in
  `status_detail` / `block_detail`, next to the normalised status — so a
  reader can see we didn't invent the characterisation.
- Status changes are inferred only from what the source itself changed to; the
  pipeline never guesses a reason that the source did not state (see the NHAI
  adapter's `cancelled` handling: it does not claim to know *why* a contract
  was terminated when the source doesn't say).

## Map and boundary compliance

India's Geospatial Guidelines (2021) and the National Geospatial Policy (2022)
concern themselves mainly with *survey and acquisition* of geospatial data
above certain accuracy thresholds by Indian and foreign entities, not with
merely *displaying* a globe. The practical risk for this project is narrower
and older: **depicting national boundaries incorrectly** (an issue under the
Criminal Law Amendment Act, 1961, historically enforced against maps showing
Jammu & Kashmir, Aksai Chin, or Arunachal Pradesh other than as per the
Survey of India's official depiction).

Concrete choices made here to stay safe:
- The bundled gazetteer (`pipeline/ref/india_places.json`) contains **point
  centroids only — no boundary polygons at all.** There is nothing in this
  repository that draws a national or state border.
- If a future version adds a basemap or boundary layer, it must use a source
  that follows the Survey of India's official depiction (or omit boundaries
  entirely and rely on the night-lights texture, as the current globe does).
- Never use a third-party basemap tile provider's default boundary rendering
  for India without checking it matches the official depiction first —
  several popular free providers do not.

## Travel-planning framing

If a "plan a trip around this" feature is ever built: do not suggest visiting
active construction sites, border-area infrastructure, or anything flagged in
a source as security-sensitive. Restrict any such feature to completed,
publicly-accessible landmarks (a commissioned bridge, a museum, a completed
expressway service area), not live project sites.
