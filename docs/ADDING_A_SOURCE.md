# Adding a source

An adapter's whole job: `fetch()` the source, `parse()` it into canonical
records. It never touches the store and never prints — that's `run.py`'s job.

## 1. Verify the source manually first, with curl or a browser

Before writing any code, confirm by hand:
- Does it actually return data with no login, or with a free API key you can
  commit instructions for (never commit the key itself)?
- What does an empty/error response look like? (So the adapter can tell
  "no results" from "the source broke.")
- Is there a stable per-record identifier? If not, what's the most stable
  substitute (see `pipeline/core/ids.py`'s title-fingerprint fallback)?
- Does it carry any location information at all — coordinates, a district
  name, even just a state? If genuinely none, the gazetteer fallback in
  `pipeline/core/gazetteer.py` will do state-centroid geocoding from the
  title text, but check first.
- What licence or terms, if any, are stated? Write it down even if the answer
  is "none stated" — see `docs/LEGAL.md` for what that means in practice.

Document what you found in `docs/SOURCES.md`, including dead ends.

## 2. Write the adapter

Copy `pipeline/adapters/nhai_geoserver.py` as a starting template — it shows
the pattern for: joining two related endpoints, mapping a source's own status
vocabulary onto the canonical one while preserving the verbatim original,
deriving geometry with an honest confidence label, and falling back to the
gazetteer when the source has no coordinates.

Required on every `Adapter` subclass: `source_id`, `source_name`,
`source_url`, `publisher`, `upstream_cadence`, `access_mode`, `licence`.
These surface directly in the UI footer and in `meta.json` — don't guess them.

```python
class MyAdapter(Adapter):
    source_id = "my_source"       # becomes the id prefix; never change once shipped
    ...
    def fetch(self):
        from ..core.fetch import fetch as http_fetch
        res = http_fetch("https://example.gov.in/api/...")
        if not res.ok:
            raise SourceUnavailable(res.note)
        return res.json()

    def parse(self, raw):
        for row in raw["items"]:
            rec = self.new_record(row["id"], row["name"], page_url=row.get("url"))
            rec["sector"] = "..."
            rec["status"] = MY_STATUS_MAP.get(row["status"], "unknown")
            rec["status_detail"] = row["status"]     # verbatim, always
            self.geocode(rec, extra_text=row.get("location", ""))
            yield schema.derive(rec)
```

## 3. Register it

Add the import and the class to `ADAPTERS` in `pipeline/run.py`. Order there
only matters for merge tie-breaking (later = more authoritative).

## 4. Test it

- Add offline tests for anything with logic worth locking down: a status map,
  a cost parser, a geometry fallback. Follow `TestNhaiAdapterOffline` as the
  pattern — no network calls in the test suite.
- Run it for real once: `python3 -m pipeline.run ingest --only my_source` and
  actually read a few resulting records in `data/derived/details.json`.
  Zero records is a bug in the adapter or a change in the source, not success.

## 5. Rules that are not optional

- **Never fabricate a field the source doesn't provide.** If a source has no
  delay reason, leave `block_reason` as `unknown` — don't infer one from the
  status alone (see the NHAI adapter's handling of `Terminated`, which
  explicitly says the reason is not stated rather than guessing "funds" or
  "contractor").
- **An empty parse is a failure.** Raise `SchemaDrift`, don't return `[]`.
- **Every record needs provenance.** `self.new_record()` sets this up for
  you automatically — don't strip it out.
- **Coordinates get validated against the India bounding box** in
  `schema.validate()`. If your source hands you lat/lon in the wrong order
  (a very common mistake), this will catch it — don't work around the check,
  fix the mapping.
