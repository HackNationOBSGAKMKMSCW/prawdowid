const MONTHS = [
  'stycznia',
  'lutego',
  'marca',
  'kwietnia',
  'maja',
  'czerwca',
  'lipca',
  'sierpnia',
  'września',
  'października',
  'listopada',
  'grudnia',
];

/** `2019-06-03` → `3 czerwca 2019`. */
export function formatDate(iso?: string): string {
  if (!iso) return '';
  const [year, month, day] = iso.split('-').map(Number);
  if (!year || !month || !day) return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/** Polska odmiana przez liczby: 1 rzecz, 2 rzeczy, 5 rzeczy. */
export function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const d = n % 10;
  const h = n % 100;
  return d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
}

/** Skraca długi tekst do `max` znaków, dodając wielokropek. */
export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 3)}…` : text;
}

export function isUrl(text: string): boolean {
  return /^(https?:\/\/|www\.)\S+$/i.test(text.trim());
}
