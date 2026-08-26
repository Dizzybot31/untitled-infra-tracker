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

export function delayText(months) {
  if (months == null) return null;
  if (months <= 0) return 'On or ahead of original schedule';
  if (months < 12) return months + ' month' + (months === 1 ? '' : 's') + ' behind original schedule';
  const y = Math.floor(months / 12), m = months % 12;
  return y + ' year' + (y === 1 ? '' : 's') + (m ? ' ' + m + ' mo' : '') + ' behind original schedule';
}

export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function titleCase(s) {
  return String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
