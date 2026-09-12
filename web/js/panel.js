// The detail panel.
//
// History: an earlier version promised slip and cost-overrun figures that no
// source could populate, so both were removed. MoSPI's PAIMANA register now
// publishes an original target date and an original sanctioned cost, so they
// come back - but STRICTLY GATED PER RECORD. Most projects here still have no
// baseline, and the absence of a slip figure must never read as "on schedule".
// That is why the no-baseline case gets its own positively-stated sentence
// rather than simply rendering nothing.
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

  // Only where the source actually publishes a baseline.
  if (r.original_completion_date && r.delay_months > 0) {
    figures.push(fig('Slip against original plan',
      `${r.delay_months} months later than ${monthYear(r.original_completion_date)}`,
      null, r.delay_months >= 12));
  }
  // The 1% floor is not cosmetic: many rows land inside it purely because the
  // original cost is an integer and the revised cost a decimal.
  const costInconsistent = d && (d.tags || []).includes('cost_figures_inconsistent');
  if (costInconsistent && d.cost_original_inr_crore) {
    figures.push(fig('Cost', crore(d.cost_inr_crore),
      `${crore(d.cost_original_inr_crore)} originally sanctioned`, true));
  }
  const overrun = !costInconsistent && d && d.cost_overrun_pct;
  if (overrun != null && Math.abs(overrun) >= 1 && d.cost_original_inr_crore) {
    figures.push(fig(
      overrun > 0 ? 'Cost above original sanction' : 'Cost below original sanction',
      `${Math.abs(overrun)}%`,
      `${crore(d.cost_original_inr_crore)} sanctioned, ${crore(d.cost_inr_crore)} now`,
      overrun > 0));
  }

  const blockHtml = (r.block_reason || (d && d.block_detail)) ? `
    <div class="p-block">
      <div class="k">${esc(BLOCK_REASON_LABEL[r.block_reason] || 'Obstruction')}</div>
      <div class="v">${esc((d && d.block_detail) || 'The source records an obstruction but gives no further detail.')}</div>
    </div>` : '';

  const pastDueNote = scheduleNote(r, d)
    + (costInconsistent ? `<p class="note">The source publishes an original cost of
        ${esc(crore(d.cost_original_inr_crore))} and a current cost of ${esc(crore(d.cost_inr_crore))}.
        We show both and calculate no overrun, because the two figures are not
        consistent with each other at source.</p>` : '');

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

// Five cases, because the honest thing to say differs in each and a blank must
// never be mistaken for "fine".
function scheduleNote(r, d) {
  const orig = r.original_completion_date;
  const rev = r.revised_completion_date;
  const noRevised = d && (d.tags || []).includes('no_revised_date');
  const inverted = d && (d.tags || []).includes('revised_earlier_than_original');

  if (orig && inverted) {
    return `<p class="note">The source publishes an original date of ${esc(monthYear(orig))} and a
      revised date of ${esc(monthYear(rev))} — earlier than the original. We show both and
      calculate nothing, because the source disagrees with itself.</p>`;
  }
  if (orig && noRevised) {
    return `<p class="note">This is the original target date. The source has published no revised
      date for this project, which is not the same as the project being on time.</p>`;
  }
  if (orig && r.delay_months > 0) {
    return `<p class="note">Originally due ${esc(monthYear(orig))}. The source now publishes
      ${esc(monthYear(rev))} — ${r.delay_months} months later than the original plan.</p>`;
  }
  if (orig) {
    return `<p class="note">Originally due ${esc(monthYear(orig))}, and that is still the date the
      source publishes. It has not been revised.</p>`;
  }
  // No baseline: the common case, and the one that must be stated out loud.
  return `<p class="note">No original target date is published for this project, so there is no
    slip figure — and that absence is not the same as being on schedule. ${
      r.bucket === 'past_due'
        ? 'We can tell you only that the date the source publishes today has passed.'
        : 'We can show only the completion date the source publishes today.'}</p>`;
}

function fig(k, v, sub, alarm) {
  return `<div class="fig${alarm ? ' alarm' : ''}">
    <div class="k">${esc(k)}</div>
    <div class="v">${esc(v)}</div>
    ${sub ? `<div class="k sub">${esc(sub)}</div>` : ''}
  </div>`;
}
