import { CDN, TEXTURES, STATUS_COLOR } from './config.js';
import { crore, esc } from './format.js';

// India-centred opening view.
const HOME = { lat: 21.5, lng: 79.0, altitude: 1.75 };

// Cost drives spike height on a log scale: a ₹1 lakh crore corridor should read
// as dramatically bigger than a ₹500 crore bypass without a linear scale making
// everything else invisible.
function altitudeFor(d) {
  const c = d.cost_inr_crore;
  if (!c || c <= 0) return 0.012;
  return Math.min(0.42, 0.012 + Math.log10(c) * 0.038);
}

function colorFor(d) {
  return STATUS_COLOR[d.status] || STATUS_COLOR.unknown;
}

function tooltip(d) {
  const cost = crore(d.cost_inr_crore);
  return `
    <div style="font:13px -apple-system,sans-serif;background:rgba(8,12,20,.94);
                border:1px solid rgba(255,255,255,.14);border-radius:9px;
                padding:8px 10px;max-width:19rem;color:#e8edf6;
                box-shadow:0 10px 30px rgba(0,0,0,.5)">
      <div style="font-weight:600;line-height:1.35">${esc(d.title)}</div>
      <div style="color:#96a2b8;font-size:11.5px;margin-top:3px">
        ${esc(d.state || '')}${cost ? ' · ' + esc(cost) : ''}
      </div>
      <div style="color:${colorFor(d)};font-size:11px;margin-top:3px">
        ${esc(String(d.status).replace(/_/g, ' '))}
      </div>
    </div>`;
}

export async function createGlobe(el, { onSelect }) {
  let Globe;
  try {
    Globe = (await import(CDN.globeGl)).default;
  } catch (err) {
    throw new Error(
      `Could not load the globe library from ${CDN.globeGl}. ` +
      `This page needs network access to that CDN on first load. (${err.message})`
    );
  }

  // globe.gl v2 supports both the constructor and the curried factory form.
  let g;
  try {
    g = new Globe(el);
  } catch {
    g = Globe()(el);
  }

  g.globeImageUrl(TEXTURES.earthNight)
    .bumpImageUrl(TEXTURES.bump)
    .backgroundImageUrl(TEXTURES.sky)
    .backgroundColor('#05070c')
    .showAtmosphere(true)
    .atmosphereColor('#2f7fd4')
    .atmosphereAltitude(0.19)
    .pointOfView(HOME, 0);

  g.pointLat('lat').pointLng('lng')
    .pointColor(colorFor)
    .pointAltitude(altitudeFor)
    .pointRadius(0.22)
    .pointsTransitionDuration(450)
    .pointLabel(tooltip)
    .onPointClick((d) => onSelect(d.id));

  // Halted projects pulse red; contested-but-proceeding ones pulse amber.
  g.ringLat('lat').ringLng('lng')
    .ringColor((d) => {
      const [r, gr, b] = d.is_blocked ? [239, 64, 86] : [245, 165, 36];
      return (t) => `rgba(${r},${gr},${b},${Math.max(0, 1 - t)})`;
    })
    .ringMaxRadius(3.2)
    .ringPropagationSpeed(1.1)
    .ringRepeatPeriod(1400);

  g.arcStartLat('startLat').arcStartLng('startLng')
    .arcEndLat('endLat').arcEndLng('endLng')
    .arcColor((d) => {
      const c = STATUS_COLOR[d.status] || STATUS_COLOR.unknown;
      return [c + '00', c, c + '00'];
    })
    .arcStroke(0.45)
    .arcAltitudeAutoScale(0.42)
    .arcDashLength(0.55)
    .arcDashGap(0.25)
    .arcDashAnimateTime(3200)
    .arcLabel((d) => tooltip(d))
    .onArcClick((d) => onSelect(d.id));

  g.labelLat('lat').labelLng('lng')
    .labelText('title')
    .labelSize(0.42)
    .labelDotRadius(0)
    .labelColor(() => 'rgba(232,237,246,0.75)')
    .labelResolution(2)
    .labelAltitude((d) => altitudeFor(d) + 0.006);

  const controls = g.controls();
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.32;
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.minDistance = 160;

  // Stop spinning as soon as the user takes hold of the globe.
  let userTook = false;
  el.addEventListener('pointerdown', () => {
    if (!userTook) { userTook = true; controls.autoRotate = false; api.onSpinStop && api.onSpinStop(); }
  });

  const resize = () => g.width(el.clientWidth).height(el.clientHeight);
  resize();
  window.addEventListener('resize', resize);

  const api = {
    globe: g,
    onSpinStop: null,
    setPoints(rows) {
      g.pointsData(rows);
      g.ringsData(rows.filter((r) => r.is_blocked || r.block_reason));
      const labelled = [...rows]
        .filter((r) => r.cost_inr_crore)
        .sort((a, b) => b.cost_inr_crore - a.cost_inr_crore)
        .slice(0, 10);
      g.labelsData(labelled);
    },
    setArcs(arcs) { g.arcsData(arcs); },
    setSpin(on) { controls.autoRotate = on; },
    focus(row, ms = 900) {
      g.pointOfView({ lat: row.lat, lng: row.lng, altitude: 0.62 }, ms);
    },
    home(ms = 900) { g.pointOfView(HOME, ms); },
  };
  return api;
}
