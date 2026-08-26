# ADR 0003: SQLite + committed static JSON, no server, no hosted database

**Status:** accepted

## Context
The product needs: (a) a change log so "this deadline slipped" is answerable,
and (b) something a static globe frontend can load fast, for free, forever.
Those are different jobs and don't need the same technology.

## Decision
- **`data/tracker.sqlite`** is the pipeline's working database: one row per
  project (current state) plus an append-only `changes` table. It is a build
  artifact — gitignored, rebuilt by re-running `ingest`, uploaded as a CI
  artifact for debugging, never committed.
- **`data/derived/*.json`** is the publish target: plain GeoJSON + JSON,
  written by `pipeline/core/publish.py`, and it IS committed. Git history of
  this directory is the audit trail — the "git scraping" pattern. The
  frontend fetches these files directly from a CDN (GitHub Pages); there is no
  API server in production.

## Consequences
- No hosted database to pay for, back up, or lose access to.
- Every historical data state is a `git log -p -- data/derived` away, for
  free, forever, with a timestamp and (via CI) an identifiable commit.
- This does not scale past a point: once the dataset is large enough that
  `projects.geojson` is too big to ship to every visitor, the fix is vector
  tiles (pmtiles) served from object storage or a CDN, not a backend API.
  Roughly: fine into the tens of thousands of features, reconsider well before
  that.
- SQLite is not safely writable by two processes at once. The scheduled
  refresh workflow (`refresh.yml`) uses `concurrency: group: refresh` to
  guarantee only one ingest job runs at a time.
