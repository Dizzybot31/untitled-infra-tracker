// The detail panel.
//
// The previous version promised capabilities the data does not have:
//   - a cost_overrun_pct figure, non-null on 0 of 1,849 records
//   - a delay_months alarm, populated on 9 (all hand-entered seed rows)
//   - a "What changed" section whose empty state apologised at length
// All three are gone. What replaces them is narrower and true: the completion
// date the source publishes today, and how long ago it passed.
//
// Provenance and location-confidence are untouched and, on narrow screens, now
// sit ABOVE the details block so they land in the first screenful.

import { STATUS_LABEL, SECTOR_LABEL, BLOCK_REASON_LABEL, GEO_CONFIDENCE_NOTE, BUCKET_COLOR } from './config.js';
import { crore, monthYear, dateTime, agoText, esc, titleCase, num } from './format.js';

export function renderPanel(el, view, { onClose, onSelect }) {
  if (!view) { el.hidden = true; el.innerHTML = ''; return; }
  el.innerHTML = view.kind === 'list' ? listMarkup(view) : projectMarkup(view);
  el.hidden = false;
  el.scrollTop = 0;

  el.querySelector('.close').addEventListener('click', onClose);
  el.querySelectorAll('[data-goto]').forEach((b) =>
    b.addEventListener('click', () => onSelect(b.dataset.goto)));

  const h = el.querySelector('#panel-title');
  if (h) h.focus();
}

// --- a coordinate stack or a state group -----------------------------------
function listMarkup(v) {
  return `
    <button class="close" aria-label="Close">&times;</button>
    <h2 id="panel-title" tabindex="-1">${esc(v.heading)}</h2>
    <p class="p-sub">${esc(v.sub)}</p>
    <ul class="plist">
      ${v.members.map((m) => `
        <li>
          <button data-goto="${esc(m.id)}">
            <span class="pl-dot" style="background:${BUCKET_COLOR[m.bucket]}"></span>
            <span class="pl-title">${esc(m.title)}</span>
            <span class="pl-meta">${esc([crore(m.cost_inr_crore),
              m.overdueMonths > 0 ? agoText(m.overdueMonths) + ' past due' : null]
              .filter(Boolean).join(' · '))}</span>
          </button>
        </li>`).join('')}
    </ul>`;
}

// --- one project ------------------------------------------------------------
function projectMarkup(v) {
  const r = v.row;              // always present, from the already-loaded geojson
  const d = v.detail;           // may still be loading
  const color = BUCKET_COLOR[r.bucket];

  const figures = [];

  const cost = crore(r.cost_inr_crore);
  if (cost) figures.push(fig('Cost', cost));

  // The schedule figure. This is the product's central claim, so its wording is
  // exact: it is the date the source publishes TODAY, not a baseline comparison.
  if (r.bucket === 'past_due') {
    figures.push(fig('Completion date, as published',
      `${monthYear(r.revised_completion_date)} · ${agoText(r.overdueMonths)}`,
      null, true));
  } else if (r.revised_completion_date) {
    figures.push(fig('Completion date, as published', monthYear(r.revised_completion_date)));
  } else if (r.lifecycle === 'building') {
    figures.push(fig('Completion date', 'Not published by this source'));
  }

  if (d && d.progress_pct != null) figures.push(fig('Physical progress', d.progress_pct + '%'));

  const blockHtml = (r.block_reason || (d && d.block_detail)) ? `
    <div class="p-block">
      <div class="k">${esc(BLOCK_REASON_LABEL[r.block_reason] || 'Obstruction')}</div>
      <div class="v">${esc((d && d.block_detail) || 'The source records an obstruction but gives no further detail.')}</div>
    </div>` : '';

  const pastDueNote = r.bucket === 'past_due' ? `
    <p class="note">This is the completion date the source publishes today. It does not publish an
    original sanctioned date, so we cannot tell you how far this project has slipped — only that
    this date has passed.</p>` : '';

  const notDrawn = r.lifecycle === 'open' ? `
    <p class="note">Already open${r.revised_completion_date ? ' since ' + esc(monthYear(r.revised_completion_date)) : ''}
    — not shown on the globe by default, which shows work in progress and work that has stopped.</p>` : '';

  const facts = d ? [
    ['Sector', SECTOR_LABEL[d.sector] || titleCase(d.sector)],
    ['State', d.admin && d.admin.state],
    ['District', d.admin && d.admin.district],
    ['Executing agency', d.executing_agency],
    ['Ministry', d.ministry],
    // Kept behind a guard so it lights up on its own if a source ever starts
    // publishing baselines. Fires on 10 records today.
    ['Originally scheduled', d.original_completion_date ? monthYear(d.original_completion_date) : null],
  ].filter(([, x]) => x) : [];

  const provHtml = d ? (d.provenance || []).map((p) => `
    <div class="prov">
      <div><a href="${esc(p.source_url)}" target="_blank" rel="noopener noreferrer">${esc(p.source_name || p.source_id)}</a></div>
      <div class="when">retrieved ${esc(dateTime(p.retrieved_at))}</div>
      ${p.note ? `<div class="note-sm">${esc(p.note)}</div>` : ''}
    </div>`).join('') : `<div class="prov placeholder">Loading source record…</div>`;

  const unverified = d && (d.tags || []).includes('unverified');

  return `
    <button class="close" aria-label="Close">&times;</button>
    <div class="p-badges">
      <span class="badge" style="color:${color}">${esc(STATUS_LABEL[r.status] || r.status)}</span>
      ${unverified ? '<span class="badge caution">Unverified seed data</span>' : ''}
    </div>
    <h2 id="panel-title" tabindex="-1">${esc(r.title)}</h2>
    <div class="p-sub">${esc([r.state, d && d.admin && d.admin.district].filter(Boolean).join(' · '))}</div>
    ${blockHtml}
    ${figures.length ? `<div class="p-figures">${figures.join('')}</div>` : ''}
    ${pastDueNote}
    ${notDrawn}

    <h3>Where this came from</h3>
    ${provHtml}

    <h3>Location confidence</h3>
    <p class="geo-note">${esc(GEO_CONFIDENCE_NOTE[r.geo_confidence] || '')}
      ${d && d.geo_note ? '<br>' + esc(d.geo_note) : ''}</p>

    ${facts.length ? `<h3>Details</h3><dl class="kv">${
      facts.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${esc(x)}</dd>`).join('')}</dl>` : ''}`;
}

function fig(k, v, sub, alarm) {
  return `<div class="fig${alarm ? ' alarm' : ''}">
    <div class="k">${esc(k)}</div>
    <div class="v">${esc(v)}</div>
    ${sub ? `<div class="k sub">${esc(sub)}</div>` : ''}
  </div>`;
}
