// Single place for the things you will want to change.
//
// Dependencies load as ES modules from a CDN so this app needs no build step
// and no npm install - open index.html through any static server and it runs.
// Pin exact versions before you rely on this in production; see
// docs/adr/0002-frontend.md for the Vite migration path.
// Versions verified live on the npm registry on 2026-08-25:
//   globe.gl 2.46.2 | three-globe 2.45.2 | three 0.185.1 | deck.gl 9.3.10
// Pinned exactly so a CDN-side major bump cannot silently break the page.
// Note if you later add three.js postprocessing: postprocessing@6.39.4 declares
// peerDependencies three ">=0.168.0 <0.186.0", which three@0.185.1 is one minor
// release away from violating.
export const CDN = {
  globeGl: 'https://esm.sh/globe.gl@2.46.2',
};

// Texture URLs. three-globe ships these example textures; swap for NASA Blue
// Marble / GIBS imagery if you want higher resolution or full offline hosting.
export const TEXTURES = {
  earthNight: 'https://unpkg.com/three-globe/example/img/earth-night.jpg',
  earthDay: 'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
  bump: 'https://unpkg.com/three-globe/example/img/earth-topology.png',
  sky: 'https://unpkg.com/three-globe/example/img/night-sky.png',
};

export const DATA = {
  projects: '../data/derived/projects.geojson',
  corridors: '../data/derived/corridors.geojson',
  details: '../data/derived/details.json',
  changes: '../data/derived/changes.json',
  meta: '../data/derived/meta.json',
};

// Status palette. Two families on purpose: the product is "what is being
// built" (cool colours) versus "what is not happening" (warm colours).
export const STATUS_COLOR = {
  proposed:          '#8b7cf6',
  approved:          '#7c8cf8',
  cleared:           '#5aa9f8',
  tendered:          '#41b8e8',
  awarded:           '#2fc6c0',
  under_construction:'#22d39a',
  commissioned:      '#7fe3b8',
  stalled:           '#f5a524',
  blocked:           '#f26d3d',
  rejected:          '#ef4056',
  withdrawn:         '#c2456b',
  cancelled:         '#8b2f4a',
  unknown:           '#6b7280',
};

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
  site: 'Site-level location, derived.',
  city: 'Placed at the named town or city, not the exact site.',
  district: 'Placed at the district centre, not the exact site.',
  state: 'Placed at the state centroid. The real location within the state is unknown.',
  none: 'No location could be determined.',
};
