// Indian numbering. Input is always INR crore.
//   1,20,000 crore -> "₹1.2 lakh cr"    55,656 crore -> "₹55,656 cr"
export function crore(v) {
  if (v == null || Number.isNaN(v)) return null;
  if (v >= 100000) {
    return '₹' + (v / 100000).toFixed(2).replace(/\.?0+$/, '') + ' lakh cr';
  }
  return '₹' + Math.round(v).toLocaleString('en-IN') + ' cr';
}

export function monthYear(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

export function dateTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}

// Replaces delayText(), which was deleted outright rather than reworded.
// Every string delayText could produce ended in "behind original schedule" - a
// claim about slip against a baseline. Only 10 of 1,849 records have an original
// date, so that phrasing was unsupportable for 99.5% of the corpus. This says
// only how long ago a published date passed, which is a fact we actually hold.
export function agoText(months) {
  if (months == null || months <= 0) return null;
  if (months < 12) return `${months} month${months === 1 ? '' : 's'} ago`;
  const y = Math.floor(months / 12), m = months % 12;
  return `${y} yr${m ? ' ' + m + ' mo' : ''} ago`;
}

export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function titleCase(s) {
  return String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function num(n) {
  return Number(n || 0).toLocaleString('en-IN');
}
