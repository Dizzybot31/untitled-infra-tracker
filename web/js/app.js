// Wiring.
//
// State is now six fields. It was: sectors Set, statuses Set, minCost, half,
// showCorridors, hideVague, spin, selected - driving 29 controls whose combined
// effect nobody could predict. The filter model is one three-way view plus one
// opt-in layer.

import { loadCore, loadLattice, detailFor, primeDetails, groupLocated, groupStates } from './data.js';
import { createGlobe } from './globe.js';
import { renderPanel } from './panel.js';
import { BUCKET_COLOR, BUCKET_LABEL, BUCKET_ORDER } from './config.js';
import { crore, dateTime, esc, num } from './format.js';

const $ = (id) => document.getElementById(id);

const state = {
  rows: [], meta: null, asOf: 0,
  view: 'all',        // all | past_due | stopped
  showOpen: false,    // the 1,122 already-open projects, opt-in
  selected: null,
};

let globe = null;

boot();

async function boot() {
  try {
    const core = await loadCore();
    Object.assign(state, core);

    globe = createGlobe($('globe'), { onSelect: select, onSelectState: selectGroup });

    buildChrome();
    apply();

    // Reveal the chrome, then drop the pitch card. Deliberately NOT gated on
    // requestAnimationFrame: rAF does not fire in a background tab, so a visitor
    // who opens the site in a new tab and switches to it later would find it
    // still showing the loading card.
    document.querySelector('.topbar').removeAttribute('hidden');
    $('viewbar').hidden = false;
    $('boot').classList.add('gone');
    setTimeout(() => { $('boot').hidden = true; }, 650);
    globe.settle();

    // Texture and richer records, both after the marks are on screen.
    loadLattice().then((arcs) => globe.setLattice(arcs));
    const idle = window.requestIdleCallback || ((f) => setTimeout(f, 1200));
    idle(() => primeDetails());

    window.addEventListener('popstate', () => {
      const id = location.hash.slice(1);
      id ? select(id, true) : closePanel(true);
    });
    if (location.hash.length > 1) select(location.hash.slice(1), true);
  } catch (err) {
    console.error(err);
    $('boot').hidden = true;
    $('fatal').hidden = false;
    $('fatal-body').innerHTML = esc(err.message || String(err)) +
      '<br><br>If you opened this file directly from disk, ES modules and <code>fetch</code> are ' +
      'blocked by the browser. Serve it instead: <code>python3 -m http.server 8777</code> from the ' +
      'repository root, then open <code>http://localhost:8777/web/</code>.';
  }
}

// ---------------------------------------------------------------------------
// The census. These four numbers partition the drawn set exactly, which is what
// lets them sit side by side without reading as a false partition. They are
// computed here, never hardcoded in markup, so they cannot ship stale.
function census() {
  const c = { past_due: 0, stopped: 0, on_schedule: 0, no_date: 0, open: 0, unstated: 0 };
  for (const r of state.rows) {
    if (r.lifecycle === 'open') c.open++;
    else if (r.lifecycle === 'unstated') c.unstated++;
    else c[r.bucket]++;
  }
  c.drawn = c.past_due + c.stopped + c.on_schedule + c.no_date;
  c.building = c.past_due + c.on_schedule + c.no_date;
  return c;
}

function buildChrome() {
  const c = census();

  $('boot-counts').textContent =
    `${num(c.building)} being built right now. ${num(c.past_due)} are already past the completion date their own source publishes.`;

  // The key row IS the legend. There is no separate legend box, so the colour
  // key can never be hidden on mobile the way the old one was.
  $('key').innerHTML = BUCKET_ORDER.map((b) => `
    <span class="key-item"><span class="dot" style="background:${BUCKET_COLOR[b]}"></span>
    <b>${num(c[b])}</b> ${esc(BUCKET_LABEL[b])}</span>`).join('');

  // Naming the universe first ("All 707") stops the two subset options reading
  // as peers that should be added together.
  const segs = [
    { k: 'all', label: `All ${num(c.drawn)}`, dot: null },
    { k: 'past_due', label: `Past due ${num(c.past_due)}`, dot: BUCKET_COLOR.past_due },
    { k: 'stopped', label: `Stopped ${num(c.stopped)}`, dot: BUCKET_COLOR.stopped },
  ];
  $('seg').innerHTML = segs.map((s) => `
    <button role="radio" aria-checked="${s.k === state.view}" data-view="${s.k}"
      class="${s.k === state.view ? 'on' : ''}">
      ${s.dot ? `<span class="dot" style="background:${s.dot}"></span>` : ''}${esc(s.label)}
    </button>`).join('');
  $('seg').querySelectorAll('[data-view]').forEach((b) =>
    b.addEventListener('click', () => {
      state.view = b.dataset.view;
      $('seg').querySelectorAll('[data-view]').forEach((x) => {
        const on = x.dataset.view === state.view;
        x.classList.toggle('on', on);
        x.setAttribute('aria-checked', String(on));
      });
      apply();
    }));

  $('caveat').textContent =
    'Past due means past the completion date the source itself publishes. No original sanction date exists, so this is not slip against a baseline.';

  const openBtn = $('toggle-open');
  openBtn.textContent = `+ Show the ${num(c.open)} already open`;
  openBtn.addEventListener('click', () => {
    state.showOpen = !state.showOpen;
    openBtn.setAttribute('aria-pressed', String(state.showOpen));
    openBtn.textContent = `${state.showOpen ? '−' : '+'} ${state.showOpen ? 'Hide' : 'Show'} the ${num(c.open)} already open`;
    apply();
  });

  $('about-btn').addEventListener('click', openAbout);
  $('scrim').addEventListener('click', closeAll);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAll(); });
  wireSearch();
}

// ---------------------------------------------------------------------------
function visible() {
  return state.rows.filter((r) => {
    if (r.lifecycle === 'unstated') return false;
    if (r.lifecycle === 'open') return state.showOpen;
    if (state.view === 'past_due') return r.bucket === 'past_due';
    if (state.view === 'stopped') return r.bucket === 'stopped';
    return true;
  });
}

function apply() {
  const rows = visible();
  globe.setPoints(groupLocated(rows));
  globe.setStates(groupStates(rows));

  // One keyboard- and screen-reader-navigable path to the same set the globe is
  // showing. The canvas alone offered none.
  $('a11y-list').innerHTML = rows.slice(0, 300).map((r) =>
    `<li><button data-goto="${esc(r.id)}">${esc(r.title)} — ${esc(BUCKET_LABEL[r.bucket] || r.bucket)}</button></li>`).join('');
  $('a11y-list').querySelectorAll('[data-goto]').forEach((b) =>
    b.addEventListener('click', () => select(b.dataset.goto)));
}

// ---------------------------------------------------------------------------
async function select(id, fromHistory) {
  const row = state.rows.find((r) => r.id === id);
  if (!row) return;
  state.selected = id;
  globe.focus(row);
  renderPanel($('panel'), { kind: 'project', row, detail: null }, { onClose: closePanel, onSelect: select });
  if (!fromHistory) history.pushState({ id }, '', '#' + id);
  const detail = await detailFor(id);
  if (state.selected === id) {
    renderPanel($('panel'), { kind: 'project', row, detail }, { onClose: closePanel, onSelect: select });
  }
}

function selectGroup(v) {
  const g = v.stack || v.state;
  const heading = v.stack ? `${g.n} projects at this point` : `${g.n} projects in ${g.state}`;
  const sub = v.stack
    ? 'These share one published coordinate.'
    : 'The source names the state but publishes no coordinates, so these are not drawn at any point.';
  state.selected = null;
  renderPanel($('panel'), { kind: 'list', heading, sub, members: g.members },
    { onClose: closePanel, onSelect: select });
}

function closePanel(fromHistory) {
  state.selected = null;
  renderPanel($('panel'), null, {});
  if (!fromHistory && location.hash) history.pushState({}, '', location.pathname);
}

function closeAll() {
  closePanel();
  $('sheet').hidden = true;
  $('scrim').hidden = true;
}

// ---------------------------------------------------------------------------
function openAbout() {
  const c = census();
  const m = state.meta;
  const costKnown = state.rows.filter((r) => r.lifecycle === 'building' && r.cost_inr_crore).length;
  const value = state.rows.filter((r) => r.lifecycle === 'building')
    .reduce((a, r) => a + (r.cost_inr_crore || 0), 0);
  const sources = (m.sources || []).map((s) =>
    `<a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_name)}</a>`).join(' · ');

  $('sheet').innerHTML = `
    <button class="close" aria-label="Close">&times;</button>
    <h2 id="sheet-title" tabindex="-1">About &amp; sources</h2>

    <h3>What this is</h3>
    <p>A tracker for Indian public infrastructure, built from government records. Every project
    carries the source it came from, a link to it, and the timestamp we fetched it.</p>

    <h3>What we count today</h3>
    <p>${num(state.rows.length)} projects: ${num(c.building)} being built, ${num(c.stopped)} stopped,
    ${num(c.open)} already open, and ${num(c.unstated)} whose status the source does not state.
    Value of work in progress: ${esc(crore(value))} — cost is published for ${num(costKnown)} of ${num(c.building)}.</p>

    <h3>What we cannot tell you yet</h3>
    <ul>
      <li>How far a project has slipped from its original plan. The sources here publish a current
      completion date and no original sanctioned date, so slip is not computable.</li>
      <li>Cost overrun. No source here publishes an original sanctioned cost.</li>
      <li>Where ${num(state.rows.filter((r) => r.geo_confidence === 'state').length)} projects
      actually are. The source names a state and no coordinates, so they are drawn as a circle over
      the state with a count, never as a point.</li>
      <li>What changed over time. Change tracking begins on the second pipeline run.</li>
    </ul>

    <h3>Coverage</h3>
    <p>This is not yet a picture of all Indian infrastructure. Most of it is national-highway
    contracts, plus a small number of hand-checked flagship projects marked
    <em>Unverified seed data</em>.</p>

    <h3>Sources</h3>
    <p>${sources}</p>
    <p class="note-sm">Data generated ${esc(dateTime(m.generated_at))}. ${esc(m.disclaimer || '')}</p>`;
  $('sheet').hidden = false;
  $('scrim').hidden = false;
  $('sheet').querySelector('.close').addEventListener('click', closeAll);
  $('sheet').querySelector('#sheet-title').focus();
}

// ---------------------------------------------------------------------------
function wireSearch() {
  const input = $('search');
  const box = $('suggest');
  input.placeholder = `Search ${num(state.rows.length)} projects…`;

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { box.hidden = true; return; }
    // Searches every row, including the already-open ones the globe is not
    // drawing - so nothing in the corpus is unreachable.
    const hits = state.rows.filter((r) =>
      r.title.toLowerCase().includes(q) || (r.state || '').toLowerCase().includes(q)).slice(0, 10);
    box.innerHTML = hits.length
      ? hits.map((r) => `<button role="option" data-id="${esc(r.id)}">${esc(r.title)}
          <span class="s-meta"><span class="dot" style="background:${BUCKET_COLOR[r.bucket]}"></span>
          ${esc(r.state || '')}</span></button>`).join('')
      : '<div class="s-empty">No match</div>';
    box.hidden = false;
    box.querySelectorAll('[data-id]').forEach((b) =>
      b.addEventListener('click', () => { select(b.dataset.id); box.hidden = true; input.value = ''; }));
  });

  // focusout, not blur+timeout: the old version display:none'd the element that
  // held focus, so tabbing into a result closed the list.
  document.querySelector('.search-wrap').addEventListener('focusout', (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) box.hidden = true;
  });
}
