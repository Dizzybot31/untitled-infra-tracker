// The globe. Four colours, one height variable, one radius variable.
//
// Encoding changes from the previous version, and why:
//   HEIGHT was cost on a log scale. The middle 50% of the cost distribution
//     spanned an ~18% length difference, so it read as noise, and rows with no
//     cost drew taller than the cheapest real project. Height is now months past
//     due, which is the one quantity this product exists to show. Anything not
//     overdue is a flat puck, so the globe's entire vertical relief IS lateness.
//   RADIUS was constant, which made a stack of 15 co-located projects look like
//     one. Radius is now stack size.
//   COLOUR was 13 statuses, 90% of which fell into two near-identical greens.
//     It is now four buckets that each mean exactly one thing.

import { TEXTURES, BUCKET_COLOR } from './config.js';
import { crore, esc } from './format.js';

const HOME = { lat: 20.2, lng: 79.5, altitude: 0.98 };
const ENTRY = { lat: 20.2, lng: 79.5, altitude: 1.9 };

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = window.matchMedia('(pointer: coarse)').matches;

// Points now sit almost flat. The vertical columns are gone: they made the map
// read as a pincushion and were impossible to navigate, and the thing they
// encoded (lateness) is carried by colour instead, which works equally well
// lying down and does not occlude its neighbours.
function altitudeFor() {
  return 0.004;
}

function radiusFor(d) {
  const base = 0.16 + 0.10 * Math.sqrt(Math.max(0, (d.n || 1) - 1));
  return coarse ? base * 1.7 : base;
}

function tooltip(d) {
  const head = d.n > 1
    ? `${d.n} projects at this point`
    : esc(d.members[0].title);
  const sub = d.n > 1
    ? `tap to list them`
    : [d.members[0].state, crore(d.members[0].cost_inr_crore)].filter(Boolean).map(esc).join(' · ');
  const late = d.maxOverdue > 0
    ? `<div style="color:${BUCKET_COLOR.past_due};font-size:11px;margin-top:3px">${d.maxOverdue} months past due</div>`
    : '';
  return `<div class="tip"><div class="tip-h">${head}</div><div class="tip-s">${sub}</div>${late}</div>`;
}

function pathTooltip(d) {
  const r = d.row;
  const late = r.overdueMonths > 0
    ? `<div style="color:${BUCKET_COLOR.past_due};font-size:11px;margin-top:3px">${r.overdueMonths} months past due</div>`
    : '';
  return `<div class="tip"><div class="tip-h">${esc(r.title)}</div>
    <div class="tip-s">${esc([r.state, crore(r.cost_inr_crore)].filter(Boolean).join(' \u00b7 '))}</div>${late}</div>`;
}

function stateTooltip(d) {
  return `<div class="tip">
    <div class="tip-h">${esc(d.state)}</div>
    <div class="tip-s">${d.n} project${d.n === 1 ? '' : 's'} · location not published</div>
    <div class="tip-s" style="margin-top:4px;max-width:17rem">The source names the state but
      publishes no coordinates, so these are not drawn at any point.</div>
  </div>`;
}

export function createGlobe(el, { onSelect, onSelectState }) {
  const Globe = globalThis.Globe;
  if (typeof Globe !== 'function') {
    throw new Error('The globe library did not load. vendor/globe.gl-2.46.2.min.js is missing or failed to parse.');
  }

  const g = new Globe(el)
    .globeImageUrl(TEXTURES.earthNight)
    .backgroundColor('rgba(0,0,0,0)')   // the CSS starfield shows through; saves a 904 KB PNG
    .showAtmosphere(true)
    .atmosphereColor('#2f7fd4')
    .atmosphereAltitude(0.17)
    .pointOfView(reduceMotion ? HOME : ENTRY, 0);

  // --- located work -------------------------------------------------------
  g.pointsData([])
    .pointLat('lat').pointLng('lng')
    .pointColor((d) => BUCKET_COLOR[d.bucket])
    .pointAltitude(altitudeFor)
    .pointRadius(radiusFor)
    .pointsTransitionDuration(0)
    .pointLabel(tooltip)
    .onPointClick((d) => (d.n > 1 ? onSelectState({ stack: d }) : onSelect(d.members[0].id)));

  // --- located work that has a REAL published road shape -------------------
  // Drawn along the actual alignment rather than as a marker. Each piece is a
  // separate path; the source splits a highway into disjoint segments and
  // joining them would draw road that does not exist.
  g.pathsData([])
    .pathPoints('coords')
    .pathPointLat((p) => p[1])
    .pathPointLng((p) => p[0])
    .pathColor((d) => BUCKET_COLOR[d.bucket])
    .pathStroke((d) => (d.bucket === 'past_due' || d.bucket === 'stopped' ? 2.4 : 1.7))
    .pathPointAlt(0.0045)
    .pathResolution(2)
    .pathTransitionDuration(0)
    .pathLabel((d) => pathTooltip(d))
    .onPathClick((d) => onSelect(d.id));

  // --- unlocated work, as flat rings on the sphere -------------------------
  // Rings are used rather than DOM overlays so they foreshorten and occlude with
  // the globe instead of floating over it like UI stuck on glass.
  g.ringsData([])
    .ringLat('lat').ringLng('lng')
    .ringColor(() => () => 'rgba(93,107,130,0.42)')
    .ringMaxRadius((d) => Math.min(2.3, 0.65 + Math.sqrt(d.n) * 0.20))
    .ringPropagationSpeed(0)
    .ringRepeatPeriod(0)
    .ringAltitude(0.0015);

  // A second, clickable flat point sits at each state's centre so the disc is
  // actually hittable - rings are not pickable in globe.gl.
  g.customLayerData([]);

  // --- labels for the state discs -----------------------------------------
  g.labelsData([])
    .labelLat('lat').labelLng('lng')
    .labelText((d) => `${d.state} · ${d.n}`)
    .labelSize(0.28)
    .labelDotRadius((d) => Math.min(0.9, 0.3 + Math.sqrt(d.n) * 0.075))
    .labelColor(() => 'rgba(178,190,212,0.55)')
    .labelAltitude(0.004)
    .labelResolution(2)
    .onLabelClick((d) => onSelectState({ state: d }));

  // --- the already-open network, as faint ground ---------------------------
  g.arcsData([])
    .arcStartLat('startLat').arcStartLng('startLng')
    .arcEndLat('endLat').arcEndLng('endLng')
    .arcColor(() => ['rgba(120,140,175,0.16)', 'rgba(120,140,175,0.16)'])
    .arcStroke(0.16)
    .arcAltitude(0.002)
    .arcsTransitionDuration(0);

  const controls = g.controls();
  controls.autoRotate = false;          // never spins; there is no toggle because there is no need
  controls.enableDamping = true;
  controls.dampingFactor = 0.1;
  controls.minDistance = 150;
  controls.maxDistance = 520;

  const resize = () => g.width(el.clientWidth).height(el.clientHeight);
  resize();
  window.addEventListener('resize', resize);

  return {
    globe: g,
    setPoints(marks) { g.pointsData(marks); },
    setPaths(paths) { g.pathsData(paths); },
    setStates(states) { g.ringsData(states).labelsData(states); },
    setLattice(arcs) { g.arcsData(arcs); },
    // One easing move on load, then the camera stays put unless the user moves it.
    settle() { if (!reduceMotion) g.pointOfView(HOME, 1500); },
    focus(row) {
      g.pointOfView({ lat: row.lat, lng: row.lng, altitude: 0.55 }, reduceMotion ? 0 : 800);
    },
    home() { g.pointOfView(HOME, reduceMotion ? 0 : 700); },
  };
}
