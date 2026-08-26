import { loadAll } from './data.js';
import { createGlobe } from './globe.js';
import { renderPanel } from './panel.js';
import { STATUS_COLOR, STATUS_LABEL, SECTOR_LABEL } from './config.js';
import { crore, dateTime, esc } from './format.js';

const $ = (id) => document.getElementById(id);

const state = {
  rows: [], arcs: [], details: {}, meta: null,
  half: 'all',                 // all | building | contested | blocked
  sectors: new Set(),          // empty = all
  statuses: new Set(),         // empty = all
  minCost: 0,
  showCorridors: true,
  hideVague: false,
  selected: null,
};

let globe = null;

boot();

async function boot() {
  const status = $('boot-status');
  try {
    const data = await loadAll((m) => { status.textContent = m; });
    Object.assign(state, data);

    status.textContent = 'Building the globe…';
    globe = await createGlobe($('globe'), { onSelect: select });
    globe.onSpinStop = () => { $('toggle-spin').checked = false; };

    buildChrome();
    apply();

    $('boot').classList.add('gone');
    setTimeout(() => { $('boot').hidden = true; }, 700);
    for (const id of ['filters', 'legend', 'footer']) $(id).hidden = false;
    document.querySelector('.topbar').hidden = false;
  } catch (err) {
    console.error(err);
    window.__bootError = (err && (err.stack || err.message)) || String(err);
    $('boot').hidden = true;
    $('fatal').hidden = false;
    $('fatal-body').innerHTML =
      esc(err.message || String(err)) +
      '<br><br>If you opened this file directly from disk, ES modules and ' +
      '<code>fetch</code> are blocked by the browser. Serve it instead:<br>' +
      '<code>python3 -m http.server 8000</code> from the repository root, then ' +
      'open <code>http://localhost:8000/web/</code>.';
  }
}

// ---------- chrome ----------

function buildChrome() {
  const m = state.meta;

  $('topstats').innerHTML = `
    <div class="topstat"><div class="n">${m.counts.published}</div><div class="k">Projects</div></div>
    <div class="topstat blocked"><div class="n">${m.counts.blocked}</div><div class="k">Halted</div></div>
    <div class="topstat"><div class="n">${crore(totalCost(state.rows)) || '—'}</div><div class="k">Tracked value</div></div>`;

  chips($('sector-chips'), m.by_sector, SECTOR_LABEL, state.sectors, null);
  chips($('status-chips'), m.by_status, STATUS_LABEL, state.statuses, STATUS_COLOR);

  $('legend').innerHTML =
    Object.entries(m.by_status).map(([s]) => `
      <span class="li"><span class="dot" style="background:${STATUS_COLOR[s] || '#666'}"></span>
      ${esc(STATUS_LABEL[s] || s)}</span>`).join('') +
    `<span class="note">Spike height is project cost on a log scale.
     Pulsing rings mark blocked or stalled projects. Arcs are corridor projects,
     drawn as straight lines between endpoints, not real alignments.</span>`;

  const src = (m.sources || []).map((s) =>
    `<a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_name)}</a>`
  ).join(' · ');
  $('footer').innerHTML = `
    <span>Data generated ${esc(dateTime(m.generated_at))}</span>
    <span class="sep">|</span><span>Sources: ${src}</span>
    <span class="sep">|</span><span>${esc(m.disclaimer)}</span>`;

  // events
  document.querySelectorAll('.seg button').forEach((b) => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.seg button').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      state.half = b.dataset.half;
      apply();
    });
  });
  $('cost-range').addEventListener('input', (e) => {
    state.minCost = +e.target.value;
    $('cost-label').textContent = state.minCost ? `at least ${crore(state.minCost)}` : 'Any size';
    apply();
  });
  $('toggle-corridors').addEventListener('change', (e) => { state.showCorridors = e.target.checked; apply(); });
  $('toggle-vague').addEventListener('change', (e) => { state.hideVague = e.target.checked; apply(); });
  $('toggle-spin').addEventListener('change', (e) => globe.setSpin(e.target.checked));
  $('reset').addEventListener('click', reset);
  $('filters-toggle').addEventListener('click', () => {
    const body = $('filters-body');
    body.hidden = !body.hidden;
    $('filters-toggle').setAttribute('aria-expanded', String(!body.hidden));
  });

  wireSearch();
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closePanel(); $('suggest').hidden = true; }
  });
}

function chips(host, counts, labels, set, colors) {
  host.innerHTML = Object.entries(counts).map(([k, n]) => `
    <button class="chip" data-k="${esc(k)}">
      ${colors ? `<span class="dot" style="background:${colors[k] || '#666'}"></span>` : ''}
      ${esc(labels[k] || k)} <span class="cnt">${n}</span>
    </button>`).join('');
  host.querySelectorAll('.chip').forEach((c) => {
    c.addEventListener('click', () => {
      const k = c.dataset.k;
      if (set.has(k)) { set.delete(k); c.classList.remove('on'); }
      else { set.add(k); c.classList.add('on'); }
      apply();
    });
  });
}

function reset() {
  state.half = 'all'; state.sectors.clear(); state.statuses.clear();
  state.minCost = 0; state.hideVague = false; state.showCorridors = true;
  document.querySelectorAll('.chip.on').forEach((c) => c.classList.remove('on'));
  document.querySelectorAll('.seg button').forEach((b) =>
    b.classList.toggle('on', b.dataset.half === 'all'));
  $('cost-range').value = 0; $('cost-label').textContent = 'Any size';
  $('toggle-vague').checked = false; $('toggle-corridors').checked = true;
  globe.home();
  apply();
}

// ---------- filtering ----------

function visible() {
  return state.rows.filter((r) => {
    // Three distinct things, deliberately not conflated:
    //   halted    - the project has stopped (stalled/rejected/cancelled/withdrawn)
    //   contested - still officially proceeding, but carries a recorded
    //               obstruction: litigation, a clearance fight, land trouble
    //   building  - proceeding with nothing flagged against it
    const contested = !!r.block_reason && !r.is_blocked;
    if (state.half === 'building' && (r.is_blocked || contested)) return false;
    if (state.half === 'blocked' && !r.is_blocked) return false;
    if (state.half === 'contested' && !contested) return false;
    if (state.sectors.size && !state.sectors.has(r.sector)) return false;
    if (state.statuses.size && !state.statuses.has(r.status)) return false;
    if (state.minCost && (r.cost_inr_crore || 0) < state.minCost) return false;
    if (state.hideVague && r.geo_confidence === 'state') return false;
    return true;
  });
}

function apply() {
  const rows = visible();
  globe.setPoints(rows);
  const ids = new Set(rows.map((r) => r.id));
  globe.setArcs(state.showCorridors ? state.arcs.filter((a) => ids.has(a.id)) : []);

  const first = $('topstats').querySelector('.topstat .n');
  if (first) first.textContent = rows.length;
  const val = $('topstats').querySelectorAll('.topstat .n')[2];
  if (val) val.textContent = crore(totalCost(rows)) || '—';
  const blk = $('topstats').querySelectorAll('.topstat .n')[1];
  if (blk) blk.textContent = rows.filter((r) => r.is_blocked).length;
}

function totalCost(rows) {
  const t = rows.reduce((a, r) => a + (r.cost_inr_crore || 0), 0);
  return t > 0 ? t : null;
}

// ---------- selection ----------

function select(id) {
  state.selected = id;
  const row = state.rows.find((r) => r.id === id);
  const detail = state.details[id];
  if (row) globe.focus(row);
  renderPanel($('panel'), detail, closePanel);
}

function closePanel() {
  state.selected = null;
  renderPanel($('panel'), null);
}

// ---------- search ----------

function wireSearch() {
  const input = $('search');
  const box = $('suggest');

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { box.hidden = true; return; }
    const hits = state.rows
      .filter((r) => r.title.toLowerCase().includes(q) ||
                     (r.state || '').toLowerCase().includes(q))
      .slice(0, 12);
    if (!hits.length) {
      box.innerHTML = '<button disabled style="color:#64708a">No match</button>';
      box.hidden = false;
      return;
    }
    box.innerHTML = hits.map((r) => `
      <button data-id="${esc(r.id)}">${esc(r.title)}
        <span class="s-sector">${esc(SECTOR_LABEL[r.sector] || r.sector)} · ${esc(r.state || '')}</span>
      </button>`).join('');
    box.hidden = false;
    box.querySelectorAll('button[data-id]').forEach((b) => {
      b.addEventListener('click', () => {
        select(b.dataset.id);
        box.hidden = true;
        input.value = '';
      });
    });
  });

  input.addEventListener('blur', () => setTimeout(() => { box.hidden = true; }, 180));
}
