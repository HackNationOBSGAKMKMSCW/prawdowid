/**
 * Pętla doprecyzowania bez backendu (VITE_API_MODE=mock).
 *
 * Proste reguły jak w trybie demo bota (`whatsappAdapter/clarification.py`, `DemoClarifier`):
 * słowo o zdarzeniu („dron”, „wybuch”, „spadł”…) bez czasu albo konkretnego miejsca
 * wywołuje pytanie, a odpowiedzi są dopisywane do twierdzenia dosłownie.
 */
import type { ClarifyStep, ClarifyTurn } from './types.ts';

const MAX_ROUNDS = 2;
const MAX_CLARIFY_CHARS = 600;
const MIN_CHECK_CHARS = 8;

const EVENT_STEMS = [
  'spadl',
  'spadn',
  'dron',
  'wybuch',
  'eksploz',
  'pozar',
  'zawalil',
  'zamach',
  'atak',
  'strzelanin',
  'katastrof',
  'wypadek',
  'wykolei',
  'powodz',
  'trzesienie',
  'zestrzel',
  'ewakuac',
  'zatrzyma',
  'aresztowa',
  'rakiet',
];
const TIME_WORD =
  /^((19|20)\d{2}|wczoraj|przedwczoraj|dzis|dzisiaj|dzisiejsz|teraz|rano|wieczor|noc|godzin|temu|tydzien|tygodni|miesiac|weekend|poniedzial|wtor|srod|czwart|piat|sobot|niedziel|stycz|lut|marc|kwiet|maj|czerw|lip|sierp|wrzes|pazdziern|listopad|grud)/;
const TIME_PATTERN = /\b(19|20)\d{2}\b|\b\d{1,2}[./-]\d{1,2}\b|\bw nocy\b/;
const PREPOSITIONS = new Set([
  'w',
  'we',
  'na',
  'pod',
  'nad',
  'kolo',
  'obok',
  'niedaleko',
  'okolicach',
  'okolicy',
  'przy',
]);
const NOT_PLACES = new Set([
  'polsce',
  'polska',
  'polski',
  'kraju',
  'europie',
  'swiecie',
  'sieci',
  'internecie',
  'necie',
  'mediach',
  'telewizji',
  'radiu',
  'gazecie',
  'artykule',
  'poscie',
  'facebooku',
  'tiktoku',
  'grupie',
  'wiadomosciach',
  'prawde',
  'prawda',
  'serio',
  'tym',
  'tej',
  'ten',
  'tamtym',
  'zeszlym',
  'zeszly',
  'przyszlym',
  'ostatnim',
  'ostatnia',
  'czasie',
  'trakcie',
  'ogole',
  'pewno',
  'pewnym',
]);
const PLACE_WORDS = ['wojewodztw', 'powiat', 'gmin', 'miast', 'wsi', 'wies', 'granic', 'lotnisk'];
const FILLERS = new Set([
  'chyba',
  'nie',
  'tak',
  'to',
  'jakos',
  'gdzies',
  'raczej',
  'moze',
  'okolo',
  'czy',
]);
const DECLINE = /\b(nie wiem|nie pamietam|nie mam pojecia|obojetnie|bez znaczenia|nie znam)\b/;
const QUESTIONS = {
  czas: 'Kiedy mniej więcej to się stało (dzień, tydzień, miesiąc)?',
  miejsce: 'Gdzie to było – miasto, gmina albo region?',
} as const;

/** Małe litery bez polskich znaków. */
function fold(text: string): string {
  return text.toLowerCase().replace(/ł/g, 'l').normalize('NFKD').replace(/\p{M}/gu, '');
}

const words = (text: string) => fold(text).match(/[a-z0-9]+/g) ?? [];
const hasTime = (text: string) =>
  TIME_PATTERN.test(fold(text)) || words(text).some((w) => TIME_WORD.test(w));

function hasPlace(text: string, answer: boolean): boolean {
  const folded = words(text);
  if (folded.some((w) => PLACE_WORDS.some((stem) => w.startsWith(stem)))) return true;
  for (let i = 1; i < folded.length; i++) {
    const word = folded[i];
    if (
      PREPOSITIONS.has(folded[i - 1]) &&
      word.length >= 3 &&
      !NOT_PLACES.has(word) &&
      !TIME_WORD.test(word)
    )
      return true;
  }
  // Nazwa własna w środku zdania („Wyryki”, „Rzeszowa”).
  const raw = text.match(/[\p{L}\d]+/gu) ?? [];
  const named = raw.some((word, i) => {
    const w = fold(word);
    return (
      (i > 0 || answer) &&
      /^\p{Lu}/u.test(word) &&
      !NOT_PLACES.has(w) &&
      !FILLERS.has(w) &&
      !TIME_WORD.test(w)
    );
  });
  if (named) return true;
  // Krótka odpowiedź bez słów o czasie to najpewniej miejsce („rzeszow”).
  return (
    answer &&
    folded.length >= 1 &&
    folded.length <= 3 &&
    !folded.some((w) => TIME_WORD.test(w) || FILLERS.has(w))
  );
}

function asStatement(text: string): string {
  let claim = text
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[?!. ]+$/, '');
  claim = claim
    .replace(/^(czy\s+)?(to\s+)?(na\s*prawd[eę]|naprawd[eę]|prawda,?\s+(ze|że)|serio)\s+/i, '')
    .replace(/^czy\s+/i, '');
  return claim ? `${claim[0].toUpperCase()}${claim.slice(1)}.` : text;
}

const userTexts = (turns: ClarifyTurn[]) =>
  turns.filter((t) => t.role === 'user' && t.text.trim()).map((t) => t.text);

function step(partial: Partial<ClarifyStep> & Pick<ClarifyStep, 'status' | 'turns'>): ClarifyStep {
  const texts = userTexts(partial.turns);
  return {
    questions: [],
    missing: [],
    understood_claim: '',
    claim: '',
    skip_claim: texts[0] ?? '',
    with_details: false,
    new_topic: false,
    ...partial,
  };
}

/** Synchronicznie liczy krok pętli (eksport dla testów i trybu demo). */
export function clarifyStep(turns: ClarifyTurn[]): ClarifyStep {
  const texts = userTexts(turns);
  const [first, ...answers] = texts;
  if (!first) return step({ status: 'too_short', turns });
  if (
    !answers.length &&
    (first.trim().length > MAX_CLARIFY_CHARS || /^https?:\/\//i.test(first.trim()))
  )
    return step({ status: 'check', turns, claim: first });

  const latest = texts[texts.length - 1];
  const folded = fold(latest);
  // Nowe pełne pytanie bez szczegółów, o które pytaliśmy, to nowy temat.
  if (
    answers.length &&
    folded.trim().endsWith('?') &&
    folded.split(/\s+/).length >= 4 &&
    !hasTime(latest) &&
    !hasPlace(folded, false)
  ) {
    const fresh: ClarifyTurn[] = [{ role: 'user', text: latest }];
    if (latest.trim().length < MIN_CHECK_CHARS)
      return step({ status: 'too_short', turns: fresh, new_topic: true });
    return { ...clarifyStep(fresh), new_topic: true };
  }

  const all = texts.join(' ');
  const event = EVENT_STEMS.some((stem) => fold(all).includes(stem));
  const missing: ('czas' | 'miejsce')[] = [];
  if (event && !hasTime(all)) missing.push('czas');
  if (event && !hasPlace(first, false) && !answers.some((a) => hasPlace(a, true)))
    missing.push('miejsce');

  const base = asStatement(first);
  const resolved = answers.length ? `${base} Szczegóły: ${answers.join('; ')}.` : base;
  const declined = answers.length > 0 && DECLINE.test(folded);
  const asked = turns.filter((t) => t.role === 'bot').length;
  const skip = answers.length ? resolved : first;

  if (missing.length && !declined && asked < MAX_ROUNDS) {
    const questions = missing.map((code) => QUESTIONS[code]);
    return step({
      status: 'ask',
      turns: [...turns, { role: 'bot', text: questions.join('\n') }],
      questions,
      missing,
      understood_claim: base,
      skip_claim: skip,
    });
  }
  return step({
    status: 'check',
    turns,
    understood_claim: base,
    claim: skip,
    skip_claim: skip,
    with_details: answers.length > 0,
  });
}

export async function mockClarify(
  turns: ClarifyTurn[],
  signal?: AbortSignal,
): Promise<ClarifyStep> {
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, 700);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    });
  });
  return clarifyStep(turns);
}
