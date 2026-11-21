/**
 * Kontrakt API między frontendem a backendem Prawdowida.
 *
 *   POST   /api/check              { text }  → CheckResponse
 *   POST   /api/check/{id}/report  { reason, comment? } → 204
 *   POST   /api/masking            { text }  → MaskingResponse
 */

export type Verdict = 'confirmed' | 'false' | 'misleading' | 'insufficient' | 'unverifiable';

export interface Source {
  /** Cytat ze źródła, który potwierdza lub obala zdanie. */
  quote: string;
  /** Wydawca, np. „Narodowy Instytut Zdrowia Publicznego”. */
  publisher: string;
  /** Adres źródła. Bez adresu wydawca pokazuje się jako zwykły tekst. */
  url?: string;
  /** Rok publikacji. */
  year?: string;
  /** Kod języka źródła (BCP 47), domyślnie „pl”. */
  lang?: string;
}

export interface Claim {
  verdict: Verdict;
  /** Sprawdzane zdanie z wiadomości użytkownika. */
  text: string;
  /** Wyjaśnienie werdyktu prostym językiem. */
  explanation: string;
  sources?: Source[];
}

export type ManipulationCategory =
  | 'EMOTIONAL_LANGUAGE'
  | 'FEAR_APPEAL'
  | 'CONSPIRACY_FRAMING'
  | 'FALSE_URGENCY'
  | 'LACK_OF_SOURCE'
  | 'EXAGGERATION'
  | 'CHERRY_PICKING';

export interface ManipulationFragment {
  quote: string;
  start: number;
  end: number;
  category: ManipulationCategory | (string & {});
  explanation: string;
  confidence: number;
}

export interface ManipulationAnalysis {
  manipulation_detected: boolean;
  /** 0–100, im wyżej, tym bardziej neutralny tekst. */
  score: number;
  fragments: ManipulationFragment[];
}

export type DateIssueCode = 'OUTDATED_AS_CURRENT' | 'INTERNAL_INCONSISTENCY';

export interface DateIssue {
  code: DateIssueCode | (string & {});
  severity: 'low' | 'medium' | 'high';
  /** Pozycja w tekście, łączy problem z `ExtractedDate.start`. */
  start: number;
  source_id?: string;
  delta_days?: number;
  description?: string;
}

export interface ExtractedDate {
  start: number;
  /** Opis wydarzenia, np. „zawalenie mostu w Toruniu”. */
  what: string;
  /** Data wydarzenia według źródła, ISO `RRRR-MM-DD`. */
  source_date_from?: string;
}

export interface DatesAnalysis {
  dates_consistent: boolean;
  article_date?: string;
  issues: DateIssue[];
  extracted: ExtractedDate[];
}

export interface TextAnalysis {
  manipulation?: ManipulationAnalysis;
  dates?: DatesAnalysis;
}

export interface CheckResult {
  status: 'result';
  /** Identyfikator sprawdzenia, potrzebny do zgłoszenia błędu i usunięcia danych. */
  id?: string;
  input_type: 'text' | 'url';
  claims: Claim[];
  analysis?: TextAnalysis;
  /** Nazwy źródeł dla `DateIssue.source_id`. */
  source_names?: Record<string, string>;
}

/** Wiadomość jest za krótka lub niejasna. */
export interface CheckClarify {
  status: 'clarify';
}

/** Pytanie spoza zakresu (pogoda, zdrowie osobiste, finanse…). */
export interface CheckOutOfScope {
  status: 'out_of_scope';
}

export type CheckResponse = CheckResult | CheckClarify | CheckOutOfScope;

/** Typy danych osobowych rozpoznawane przez `backend/dataMasking`. */
export type MaskedLabel =
  | 'PESEL'
  | 'NIP'
  | 'REGON'
  | 'NR_KONTA'
  | 'KARTA'
  | 'DOWOD'
  | 'PASZPORT'
  | 'TELEFON'
  | 'EMAIL'
  | 'IP'
  | 'ADRES'
  | 'KOD_POCZTOWY'
  | 'DATA_URODZENIA'
  | 'NR_REJESTRACYJNY';

export interface MaskedEntity {
  label: MaskedLabel;
  /** Znacznik w zamaskowanym tekście, np. `[TELEFON_1]`. */
  placeholder: string;
  /** Pozycja wartości w tekście wysłanym do maskowania (backend nie odsyła samych wartości). */
  start: number;
  end: number;
}

export interface MaskingResponse {
  masked_text: string;
  entities: MaskedEntity[];
  counts: Partial<Record<MaskedLabel, number>>;
}
