# ADR 0004: Offline gazetteer first, confidence always labelled

**Status:** accepted; expect this to evolve as real adapters land

## Context
Most government project records carry no coordinates — a title like "4-laning
of NH-44 from Km 235 to Km 310, Telangana" is typical. A live geocoding API
(Nominatim, Bhuvan) would need network calls, a rate limit, and a dependency;
it would also make the pipeline non-reproducible run to run.

## Decision
`pipeline/core/gazetteer.py` is a small, offline, dependency-free lookup
against a hand-built table of Indian states and ~150 cities/places
(`pipeline/ref/india_places.json`). It tries, in order: an explicit
corridor pattern ("X to Y", "X-Y") resolved to two city points as a
`LineString`; a city name match; a state name match; nothing. Every result
carries `geo_confidence` (`exact` / `site` / `city` / `district` / `state` /
`none`) and `geo_method`, and the frontend surfaces both rather than hiding
them.

Where a source publishes its own coordinates (NHAI's alignment layer), those
are used directly and labelled `geo_confidence: site`, `geo_method:
source_latlon` — the gazetteer is a fallback, never an override.

## Consequences
- Fully offline, fully reproducible, zero rate limit, zero API key.
- Coverage is necessarily partial and coarse: a state-centroid pin is honest
  about not knowing more, but it is still just a big red dot in the middle of
  a state. This is a deliberate tradeoff of honesty over false precision.
- `schema.validate()` enforces an India bounding-box check on every point
  specifically to catch the most common real bug in this kind of code: a
  swapped lat/lon.
- **Planned evolution, not yet built:** an OSM/Nominatim lookup tier behind a
  persistent on-disk cache, used only for records the gazetteer can't place,
  respecting Nominatim's usage policy (one request per second, custom User-
  Agent, cache aggressively). This stays optional and offline-safe: if the
  network tier is unavailable, the gazetteer fallback still runs and the
  pipeline still produces output.
