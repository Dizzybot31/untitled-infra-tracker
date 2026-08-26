import {
  STATUS_COLOR, STATUS_LABEL, SECTOR_LABEL,
  BLOCK_REASON_LABEL, GEO_CONFIDENCE_NOTE,
} from './config.js';
import { crore, monthYear, dateTime, delayText, esc, titleCase } from './format.js';

export function renderPanel(el, d, onClose) {
  if (!d) { el.hidden = true; el.innerHTML = ''; return; }

  const color = STATUS_COLOR[d.status] || STATUS_COLOR.unknown;
  const unverified = (d.tags || []).includes('unverified');

  const figures = [];
  const cost = crore(d.cost_inr_crore);
  if (cost) {
    const orig = crore(d.cost_original_inr_crore);
    figures.push(fig('Current cost', cost,
      d.cost_overrun_pct ? `up ${d.cost_overrun_pct}% from ${orig}` : null,
      d.cost_overrun_pct > 0));
  }
  if (d.progress_pct != null) figures.push(fig('Physical progress', d.progress_pct + '%'));
  if (d.revised_completion_date) {
    figures.push(fig('Target completion', monthYear(d.revised_completion_date),
      d.original_completion_date ? `originally ${monthYear(d.original_completion_date)}` : null,
      (d.delay_months || 0) > 0));
  } else if (d.original_completion_date) {
    figures.push(fig('Target completion', monthYear(d.original_completion_date)));
  }
  if (d.commissioned_date) figures.push(fig('Commissioned', monthYear(d.commissioned_date)));
  if (d.delay_months != null && d.delay_months !== 0) {
    figures.push(fig('Schedule', delayText(d.delay_months), null, d.delay_months > 0, true));
  }

  const blockHtml = (d.block_reason || d.block_detail) ? `
    <div class="p-block">
      <div class="k">${esc(BLOCK_REASON_LABEL[d.block_reason] || 'Obstruction')}</div>
      <div class="v">${esc(d.block_detail || 'No further detail recorded by the source.')}</div>
    </div>` : '';

  const facts = [
    ['Sector', SECTOR_LABEL[d.sector] || titleCase(d.sector)],
    ['Subsector', d.subsector],
    ['State', d.admin && d.admin.state],
    ['District', d.admin && d.admin.district],
    ['Executing agency', d.executing_agency],
    ['Ministry', d.ministry],
    ['Sanctioned', monthYear(d.sanctioned_date)],
  ].filter(([, v]) => v);

  const history = (d.history || []).slice().reverse();
  const historyHtml = history.length ? `
    <div class="timeline">
      ${history.map((h) => `
        <div class="tl-item">
          <div class="when">${esc(dateTime(h.observed_at))}</div>
          <div class="what">${esc(titleCase(h.field))} changed from
            <strong>${esc(h.old_value ?? '—')}</strong> to
            <strong>${esc(h.new_value ?? '—')}</strong></div>
        </div>`).join('')}
    </div>` : `
    <p class="tl-empty">No changes recorded yet. This project has been seen in
    every run since ${esc(dateTime(d.first_seen))} without any tracked field
    moving. Once the pipeline has run a few times against a live source, cost
    revisions and slipped deadlines appear here.</p>`;

  const provHtml = (d.provenance || []).map((p) => `
    <div class="prov">
      <div><a href="${esc(p.source_url)}" target="_blank" rel="noopener noreferrer">${esc(p.source_name || p.source_id)}</a></div>
      <div class="when">retrieved ${esc(dateTime(p.retrieved_at))}</div>
      ${p.note ? `<div class="note">${esc(p.note)}</div>` : ''}
    </div>`).join('');

  el.innerHTML = `
    <button class="close" aria-label="Close">&times;</button>
    <div class="p-badges">
      <span class="badge" style="color:${color}">${esc(STATUS_LABEL[d.status] || d.status)}</span>
      <span class="badge sector">${esc(SECTOR_LABEL[d.sector] || d.sector)}</span>
      ${unverified ? '<span class="badge caution">Unverified seed data</span>' : ''}
    </div>
    <h2>${esc(d.title)}</h2>
    <div class="p-sub">${esc([d.admin && d.admin.district, d.admin && d.admin.state].filter(Boolean).join(', '))}</div>
    ${blockHtml}
    ${figures.length ? `<div class="p-figures">${figures.join('')}</div>` : ''}
    ${d.status_detail ? `<p class="tl-empty">${esc(d.status_detail)}</p>` : ''}

    <h3>Details</h3>
    <dl class="kv">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>

    <h3>What changed</h3>
    ${historyHtml}

    <h3>Where this came from</h3>
    ${provHtml}

    <h3>Location confidence</h3>
    <p class="geo-note">
      ${esc(GEO_CONFIDENCE_NOTE[d.geo_confidence] || '')}
      ${d.geo_note ? '<br>' + esc(d.geo_note) : ''}
    </p>`;

  el.hidden = false;
  el.scrollTop = 0;
  el.querySelector('.close').addEventListener('click', onClose);
}

function fig(k, v, sub, alarm = false, wide = false) {
  return `<div class="fig${alarm ? ' alarm' : ''}${wide ? ' wide' : ''}">
    <div class="k">${esc(k)}</div>
    <div class="v">${esc(v)}</div>
    ${sub ? `<div class="k" style="margin-top:.2rem;text-transform:none;letter-spacing:0">${esc(sub)}</div>` : ''}
  </div>`;
}
