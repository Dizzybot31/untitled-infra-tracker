// Config and vocabulary.
//
// globe.gl now loads as a single vendored UMD <script> in index.html, not as an
// ES module from a CDN. The old esm.sh import pulled 150 separate files and cost
// 5.3s before first paint; the bundle is one same-origin request.

export const TEXTURES = {
  earthNight: 'vendor/earth-night.jpg',
};

export const DATA = {
  projects: '../data/derived/projects.geojson',
  corridors: '../data/derived/corridors.geojson',
  details: '../data/derived/details.json',
  meta: '../data/derived/meta.json',
};

// ---------------------------------------------------------------------------
// The globe palette. FOUR values, not thirteen.
//
// The old palette gave 1,667 of 1,849 points two greens ~18 deltaE apart, so the
// globe read as one undifferentiated hairball. These four are the only
// distinctions the globe has to carry, and each one means exactly one thing.
//
// Critically, "no date published" is its own neutral grey rather than being
// folded into green. Green previously meant both "this is fine" and "we have no
// idea", which is the one place the product's honesty rule leaked into the
// primary visual encoding.
export const BUCKET_COLOR = {
  past_due:    '#f5a524',  // amber  - past the completion date its source publishes
  on_schedule: '#2fc6c0',  // teal   - a date is published and is still in the future
  no_date:     '#7b87a2',  // slate  - the source publishes no completion date at all
  stopped:     '#ef4056',  // red    - halted, cancelled, or carrying an obstruction
  unlocated:   '#5d6b82',  // dimmer slate - the state discs, outside the status palette
  open:        '#3f5170',  // dim    - already-open projects, only when opted in
};

export const BUCKET_LABEL = {
  past_due: 'past due',
  on_schedule: 'on schedule',
  no_date: 'no date published',
  stopped: 'stopped',
  open: 'already open',
  unstated: 'status not stated',
};

// Order matters: it is the key row order, and it is the precedence used when a
// coordinate stack has members in several buckets (worst wins, so an alarm can
// never be hidden behind a healthier neighbour).
export const BUCKET_ORDER = ['past_due', 'stopped', 'on_schedule', 'no_date'];
export const BUCKET_SEVERITY = { stopped: 3, past_due: 2, no_date: 1, on_schedule: 0,
                                 open: -1, unstated: -1 };

// ---------------------------------------------------------------------------
// Kept in full, unchanged: the panel still shows the source's own fine-grained
// status with a text label beside the swatch, where 13 values are informative
// rather than noise.
export const STATUS_LABEL = {
  proposed: 'Proposed', approved: 'Approved', cleared: 'Cleared',
  tendered: 'Tendered', awarded: 'Awarded',
  under_construction: 'Under construction', commissioned: 'Commissioned',
  stalled: 'Stalled', blocked: 'Blocked', rejected: 'Rejected',
  withdrawn: 'Withdrawn', cancelled: 'Cancelled', unknown: 'Unknown',
};

export const SECTOR_LABEL = {
  road: 'Roads', rail: 'Railways', metro: 'Metro & RRTS', power: 'Power',
  renewable: 'Renewables', port: 'Ports', airport: 'Airports',
  water: 'Water supply', irrigation: 'Irrigation', urban: 'Urban',
  telecom: 'Telecom', industrial: 'Industrial', health: 'Health',
  education: 'Education', logistics: 'Logistics', other: 'Other',
};

export const BLOCK_REASON_LABEL = {
  land_acquisition: 'Land acquisition',
  forest_clearance: 'Forest clearance',
  environment_clearance: 'Environmental clearance',
  wildlife_clearance: 'Wildlife clearance',
  litigation: 'Litigation',
  funds: 'Funding',
  contractor: 'Contractor',
  law_and_order: 'Law and order',
  geological: 'Geological or technical',
  utility_shifting: 'Utility shifting',
  rehabilitation: 'Resettlement',
  tender_failure: 'Tender failure',
  other: 'Other', unknown: 'Not stated',
};

export const GEO_CONFIDENCE_NOTE = {
  exact: 'Coordinates published by the source.',
  site: 'Site-level location, as published by the source for this alignment.',
  city: 'Placed at the named town or city, not the exact site.',
  district: 'Placed at the district centre, not the exact site.',
  state: 'The source names a state but publishes no coordinates. This project is not drawn at a point anywhere.',
  none: 'No location could be determined.',
};
