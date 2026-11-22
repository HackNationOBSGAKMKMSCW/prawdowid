const dateTime = new Intl.DateTimeFormat('pl-PL', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
const dateOnly = new Intl.DateTimeFormat('pl-PL', { day: 'numeric', month: 'short', year: 'numeric' });
const timeOnly = new Intl.DateTimeFormat('pl-PL', { hour: '2-digit', minute: '2-digit' });
const integer = new Intl.NumberFormat('pl-PL');
const relative = new Intl.RelativeTimeFormat('pl-PL', { numeric: 'auto' });

export const fmtDateTime = (iso?: string) => (iso ? dateTime.format(new Date(iso)) : '—');
export const fmtDate = (iso?: string) => (iso ? dateOnly.format(new Date(iso)) : '—');
export const fmtTime = (iso?: string) => (iso ? timeOnly.format(new Date(iso)) : '—');
export const fmtInt = (n: number) => integer.format(n);

export function fmtRelative(iso?: string): string {
  if (!iso) return '—';
  const diff = (Date.parse(iso) - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 60) return 'przed chwilą';
  if (abs < 3600) return relative.format(Math.round(diff / 60), 'minute');
  if (abs < 86_400) return relative.format(Math.round(diff / 3600), 'hour');
  return relative.format(Math.round(diff / 86_400), 'day');
}

export function fmtDuration(ms: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
}

export function fmtPln(value: number, digits = 2): string {
  return `${value.toLocaleString('pl-PL', { minimumFractionDigits: digits, maximumFractionDigits: digits })} zł`;
}

export function fmtPct(ratio: number, digits = 0): string {
  return `${(ratio * 100).toLocaleString('pl-PL', { maximumFractionDigits: digits })}%`;
}

/** Polish plural: plural(5, ['zapytanie', 'zapytania', 'zapytań']). */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n);
  if (abs === 1) return forms[0];
  const lastTwo = abs % 100;
  const last = abs % 10;
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return forms[1];
  return forms[2];
}

export function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
