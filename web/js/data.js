// Loading and shaping. Everything the globe draws is derived here, once.

import { DATA, BUCKET_SEVERITY } from './config.js';

async function getJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Lifecycle classification.
//
// These four sets partition the corpus exactly - they sum to the full row count,
// which is the property that lets the interface show counts side by side without
// inviting the reader to add a subset to its own superset.
//
// A project carrying a block_reason counts as stopped even if its status still
// says under construction: an obstruction on the record is the more important
// fact, and it keeps `stopped` consistent with what the panel shows.
export function lifecycleOf(p) {
  if (p.is_blocked || p.block_reason) return 'stopped';
  if (p.status === 'commissioned') return 'open';
  if (p.status === 'unknown') return 'unstated';
  return 'building';
}

// Within `building`, three sub-buckets by what the source says about timing.
// "no_date" is deliberately NOT merged into "on_schedule": not knowing is a
// different fact from being fine, and the globe colours them differently.
export function bucketOf(p, asOf) {
  if (p.is_blocked || p.block_reason) return 'stopped';
  // A finished project is never "past due" - its completion date being in the
  // past is the expected outcome, not a problem. Without this, every one of the
  // 1,122 commissioned rows rendered as an amber past-due mark wherever a bucket
  // colour was shown (search results, list rows).
  if (p.status === 'commissioned') return 'open';
  if (p.status === 'unknown') return 'unstated';
  const d = p.revised_completion_date;
  if (!d) return 'no_date';
  const t = Date.parse(d);
  if (Number.isNaN(t)) return 'no_date';
  return t < asOf ? 'past_due' : 'on_schedule';
}

export function monthsBetween(fromMs, toMs) {
  const a = new Date(fromMs), b = new Date(toMs);
  return (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
}

export async function loadCore(onProgress = () => {}) {
  onProgress('Reading the project register…');
  // Only what the first frame needs. details.json (2.9 MB) is deliberately not
  // here - it is one record per click, and fetching it up front put 2.9 MB on
  // the critical path for data nobody has asked for yet.
  const [fc, meta] = await Promise.all([
    getJSON(DATA.projects),
    getJSON(DATA.meta, { cache: 'no-cache' }),
  ]);

  const asOf = Date.parse(meta.generated_at) || Date.now();

  const rows = fc.features.map((f) => {
    const p = f.properties;
    const lifecycle = lifecycleOf(p);
    const bucket = bucketOf(p, asOf);
    const overdueMonths = bucket === 'past_due'
      ? monthsBetween(Date.parse(p.revised_completion_date), asOf)
      : 0;
    return {
      ...p,
      lng: f.geometry.coordinates[0],
      lat: f.geometry.coordinates[1],
      lifecycle,
      bucket,
      overdueMonths,
    };
  });

  return { rows, meta, asOf };
}

// ---------------------------------------------------------------------------
// Grouping. Two problems solved here, both of them honesty problems.
//
// 1. Co-located rows: 460 located rows collapse onto 346 distinct coordinates.
//    Drawn naively, the duplicates are invisible - a stack of 15 looks like 1.
// 2. State-only rows: 537 rows have no coordinates at all and were previously
//    drawn on their state centroid, producing fake towers (54 stacked on one
//    point in Maharashtra) that looked like real dense clusters.

export function groupLocated(rows) {
  const by = new Map();
  for (const r of rows) {
    if (r.geo_confidence === 'state' || r.geo_confidence === 'none') continue;
    if (!Number.isFinite(r.lat) || !Number.isFinite(r.lng)) continue;
    const key = `${r.lng.toFixed(4)},${r.lat.toFixed(4)}`;
    let g = by.get(key);
    if (!g) {
      g = { lat: r.lat, lng: r.lng, members: [], bucket: 'on_schedule', maxOverdue: 0, cost: 0 };
      by.set(key, g);
    }
    g.members.push(r);
    if (BUCKET_SEVERITY[r.bucket] > BUCKET_SEVERITY[g.bucket]) g.bucket = r.bucket;
    if (r.overdueMonths > g.maxOverdue) g.maxOverdue = r.overdueMonths;
    g.cost += r.cost_inr_crore || 0;
  }
  for (const g of by.values()) {
    g.n = g.members.length;
    g.id = g.members[0].id;
    g.title = g.n === 1 ? g.members[0].title : `${g.n} projects at this point`;
  }
  return [...by.values()];
}

// State-only rows become one disc per state, never a point. A dashed area plus a
// count says exactly what is known: N projects somewhere in here.
export function groupStates(rows) {
  const by = new Map();
  for (const r of rows) {
    if (r.geo_confidence !== 'state') continue;
    const st = r.state || 'Unknown state';
    let g = by.get(st);
    if (!g) g = { state: st, lat: r.lat, lng: r.lng, members: [] }, by.set(st, g);
    g.members.push(r);
  }
  for (const g of by.values()) {
    g.n = g.members.length;
    g.pastDue = g.members.filter((m) => m.bucket === 'past_due').length;
    g.stopped = g.members.filter((m) => m.bucket === 'stopped').length;
  }
  return [...by.values()].sort((a, b) => b.n - a.n);
}

// ---------------------------------------------------------------------------
// details.json, fetched once on first use and memoised. The panel opens
// immediately from the row it already has; the richer record fills in behind it.
let detailsPromise = null;
export function primeDetails() {
  if (!detailsPromise) detailsPromise = getJSON(DATA.details).catch(() => ({}));
  return detailsPromise;
}
export async function detailFor(id) {
  const all = await primeDetails();
  return all[id] || null;
}

// The faint ground lattice of already-open corridors. Loaded after first paint:
// it is texture, not information, and must never delay the marks.
export async function loadLattice() {
  try {
    const fc = await getJSON(DATA.corridors);
    return fc.features
      .filter((f) => !f.properties.is_blocked && f.properties.status === 'commissioned')
      .map((f) => {
        const c = f.geometry.coordinates;
        return {
          startLng: c[0][0], startLat: c[0][1],
          endLng: c[c.length - 1][0], endLat: c[c.length - 1][1],
        };
      });
  } catch {
    return [];
  }
}
