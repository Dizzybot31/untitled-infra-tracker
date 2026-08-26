# Untitled: Infra Tracker

**What India is building, and what it isn't.**

A 3D globe of India's public infrastructure projects, assembled from government
sources, where every number on screen can be traced back to the page it came
from and the moment it was read.

Most government dashboards tell you today's figure. They do not tell you that a
project's completion date has been pushed back four times, that its cost
estimate has doubled since sanction, or that its forest clearance was returned
by the appraisal committee two years ago. Untitled: Infra Tracker keeps the history, so the
interesting question — *what changed, and when did they tell us?* — is
answerable.

![status](https://img.shields.io/badge/status-walking%20skeleton-orange)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![deps](https://img.shields.io/badge/pipeline%20dependencies-none-green)

---

## Run it in thirty seconds

No Node, no npm, no Docker, no virtualenv, no API keys.

```bash
git clone https://github.com/dizzybot31/untitled-infra-tracker.git
cd untitled-infra-tracker
python3 -m pipeline.run all
python3 -m http.server 8777
```

Then open **http://localhost:8777/web/**.

The pipeline is standard-library Python 3.9+. The frontend is ES modules loaded
straight from a CDN. Both of those are deliberate: the biggest risk to a
side project is not technical difficulty, it is the day you come back after
three months and the toolchain no longer installs.

---

## The two halves

The product is one question asked in two directions.

| | What it shows | Where it comes from |
|---|---|---|
| **Being built** | Projects under construction, their cost, their schedule, how far behind they are | Project monitoring reports, agency dashboards, tender awards |
| **Contested** | Projects officially proceeding but carrying a recorded obstruction — litigation, a clearance fight, land trouble | Clearance registers, tribunal orders, delay-reason fields |
| **Halted** | Projects stopped, rejected, withdrawn or cancelled | Clearance rejections, quashed notifications, stalled-project reports |

Keeping *contested* separate from *halted* matters. A project can be actively
under construction and simultaneously the subject of a Supreme Court challenge.
Collapsing those into one "blocked" bucket would be the kind of small
dishonesty that makes a data product untrustworthy.

---

## Can this be real-time?

Short answer: **no, and anyone who tells you otherwise is selling something.**

"Real-time" is a property of the *source*, not of your scraper. You cannot
refresh faster than the government publishes. What is achievable:

| Source type | How often it really changes | Achievable freshness |
|---|---|---|
| Tender and award notices | Continuously | Hours |
| Clearance proposal registers | Daily to weekly | ~1 day |
| Agency dashboards | Weekly to monthly | ~1 day after they update |
| Project monitoring reports (PDF) | Monthly | Days after publication |
| Parliamentary answers, audit reports | Sessional, annual | Weeks |

So the honest promise is **"updated daily, showing you what the government last
said and when they said it"** — not a live feed. That is why every record in
Untitled: Infra Tracker carries a `retrieved_at`, and why the UI shows it rather than hiding it.
A tracker whose real value is *change over time* does not need to be live; it
needs to be **consistent, dated, and never silently wrong**.

See [`docs/SOURCES.md`](docs/SOURCES.md) for the per-source detail.

---

## What is actually built right now

This is a **walking skeleton** — the whole loop works end to end, on a small
hand-curated dataset, so that everything after this is filling in sources
rather than inventing architecture.

- ✅ Canonical schema with enforced provenance — a record with no source URL is
  rejected, not published
- ✅ SQLite store with an append-only change log, so slipped deadlines and cost
  revisions become a timeline
- ✅ Offline geocoder that labels its own uncertainty (`city` vs `state
  centroid`) instead of pretending to precision
- ✅ Conservative cross-source entity resolution, with a review queue rather
  than silent merging
- ✅ 3D globe: cost as spike height, status as colour, corridors as arcs,
  pulsing rings on obstructed projects, click-through detail with full
  provenance
- ✅ Scheduled refresh via GitHub Actions using the git-scraping pattern
- ✅ 45 tests, no dependencies
- ✅ **One real, live networked adapter**: NHAI's public GeoServer, 1,813 actual
  national highway projects with real cost, progress, status and (partial)
  geometry — no API key, verified live, see [`docs/SOURCES.md`](docs/SOURCES.md)
- ⬜ PAIMANA adapter (MoSPI's national project register — found, verified,
  currently flaky server-side; see SOURCES.md for the workaround)
- ⬜ Real corridor geometry for railways/metro (currently straight lines
  between endpoints; roads already use NHAI's own published alignment points)
- ⬜ Vector tiles, once the dataset outgrows plain GeoJSON

43 hand-curated projects ship as seed data, tagged `unverified` and badged in
the UI — high-profile projects not yet covered by a networked adapter (metro,
rail, power, ports). Everything else — currently **1,813 real national highway
projects** — comes live from NHAI's own GeoServer on every pipeline run.

---

## How it fits together

```
pipeline/
  adapters/     one per source; fetch() and parse() into canonical records
  core/
    schema.py   the canonical record, its vocabularies, and validation
    fetch.py    polite cached HTTP: robots.txt, backoff, WAF detection
    gazetteer.py  place text -> coordinates, with honest confidence labels
    ids.py      stable ids and conservative entity resolution
    store.py    SQLite + append-only change log
    publish.py  static GeoJSON/JSON for the frontend
  ref/          offline reference data (gazetteer, seed projects)
  run.py        CLI: ingest | link | publish | stats | sources | all

web/            zero-build frontend; globe.gl + ES modules, no bundler
data/derived/   published output, committed so git history is the audit trail
docs/           architecture, sources, legal, runbook, decision records
```

Commands:

```bash
python3 -m pipeline.run sources         # what adapters exist and what they are
python3 -m pipeline.run ingest --only seed
python3 -m pipeline.run link            # cross-source duplicate detection
python3 -m pipeline.run publish         # write data/derived/
python3 -m pipeline.run stats
python3 -m unittest discover -s tests
```

---

## Design commitments

These are the rules the code enforces, not aspirations.

1. **No record without provenance.** `schema.validate()` refuses to publish a
   record lacking a source URL and a retrieval timestamp.
2. **Uncertainty is displayed, not smoothed.** A project placed at a state
   centroid says so in the UI. Guessing silently is worse than not knowing.
3. **An empty scrape is a failure, not an empty world.** An adapter returning
   zero records raises rather than quietly wiping the dataset.
4. **The source's own words are preserved.** Normalised `status` sits alongside
   verbatim `status_detail`.
5. **Merging is conservative.** Name similarity alone never merges two records;
   ambiguous pairs go to a review queue.

---

## This is not investment advice

Untitled: Infra Tracker is a data visualisation of public records. It is not a recommendation
to buy, sell, or hold anything, and it is not personalised advice. Figures are
as reported by the source on the date shown and may be stale or wrong at
source. See [`docs/LEGAL.md`](docs/LEGAL.md) for attribution, licensing,
personal-data handling, and the map/boundary constraints that apply to any
project rendering Indian territory.

---

## Contributing

The highest-value contribution is a **new adapter** for a real source. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`docs/ADDING_A_SOURCE.md`](docs/ADDING_A_SOURCE.md).

## Licence

Code: [MIT](LICENSE). Data: belongs to whoever published it — see
[`docs/LEGAL.md`](docs/LEGAL.md).
