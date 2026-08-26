# Runbook

## Run everything locally

```bash
python3 -m pipeline.run all        # ingest + link + publish
python3 -m http.server 8777
open http://localhost:8777/web/
```

## Run one source only

```bash
python3 -m pipeline.run sources                        # list what's registered
python3 -m pipeline.run ingest --only nhai_geoserver    # real network calls
python3 -m pipeline.run ingest --only seed              # no network
```

The NHAI GeoServer is a real, unhardened government service (Apache Tomcat
8.5.53, no docs, no rate limiting). It has been observed to time out on large
unfiltered pulls. The adapter already requests only named columns to keep
payloads small (~0.5–1.3 MB per layer); if it starts failing, check
`data/nirmaan.sqlite`'s `runs` table for the recorded error before assuming
the source is gone.

## Diagnosing an adapter failure

Every run is recorded, success or failure:

```bash
python3 -m pipeline.run stats
sqlite3 data/nirmaan.sqlite "select * from runs order by started_at desc limit 5;"
```

An adapter that returns zero records is treated as a **failure**
(`SchemaDrift`), not an empty world — check the printed error, then verify by
hand with curl before assuming the adapter is broken:

```bash
curl -s "https://datalakew.nhai.gov.in/geoserver/NHAI/ows?service=WFS&version=2.0.0&request=GetCapabilities" | head -c 500
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Network-touching behaviour (the live NHAI fetch) is deliberately **not** in
the test suite — tests must be deterministic and runnable offline. What's
locked down instead: the status-vocabulary mapping, cost parsing, and the
geometry join/fallback logic, all with synthetic input. See
`TestNhaiAdapterOffline` in `tests/test_pipeline.py`.

## Publishing to GitHub Pages

`.github/workflows/pages.yml` deploys `web/` and `data/derived/` on every push
to `main` that touches either. No build step. First-time setup: in the repo's
Settings → Pages, set the source to "GitHub Actions."

## The scheduled refresh

`.github/workflows/refresh.yml` runs daily, ingests, links, publishes, and
commits `data/derived/` if it changed — the git-scraping pattern. Two things
that will eventually bite you:

1. GitHub disables scheduled workflows after 60 days of repo inactivity. If
   data stops updating, check Actions → the workflow → whether it's disabled,
   before assuming a source went dark.
2. Scheduled runs are queued, not punctual — expect 10–30 minute jitter. Never
   build anything that needs minute-level precision on top of this.

Trigger it manually to verify it works before waiting for the schedule:

```bash
gh workflow run refresh.yml
gh run watch
```

## Adding a new source

See `docs/ADDING_A_SOURCE.md`.
