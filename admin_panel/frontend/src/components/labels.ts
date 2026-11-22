import type {
  AlertStatus,
  AlertType,
  CaseStatus,
  CheckFlag,
  CheckOutcome,
  EvidenceStrength,
  GapStatus,
  Health,
  InputKind,
  PipelineRole,
  ProcessingRegion,
  ProviderProtocol,
  Role,
  SecurityEvent,
  Severity,
  SourceStatus,
  SourceType,
  Verdict,
} from '../api/types.ts';

/** Badge tones map to the status palette; they always come with a text label. */
export type Tone = 'neutral' | 'info' | 'good' | 'warning' | 'serious' | 'critical' | 'muted';

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Administrator',
  analyst: 'Analityk',
  user: 'Użytkownik serwisu',
};

export const VERDICT: Record<Verdict, { label: string; tone: Tone }> = {
  confirmed: { label: 'Potwierdzone', tone: 'good' },
  false: { label: 'Fałszywe', tone: 'critical' },
  misleading: { label: 'Wprowadzające w błąd', tone: 'serious' },
  insufficient: { label: 'Brak wystarczających dowodów', tone: 'neutral' },
  not_verifiable: { label: 'Nie podlega weryfikacji', tone: 'muted' },
};

export const OUTCOME: Record<CheckOutcome, { label: string; tone: Tone }> = {
  verdict: { label: 'Werdykt', tone: 'info' },
  abstained: { label: 'Wstrzymano się', tone: 'neutral' },
  technical_error: { label: 'Błąd techniczny', tone: 'warning' },
  needs_clarification: { label: 'Prośba o doprecyzowanie', tone: 'muted' },
  refused: { label: 'Odrzucone', tone: 'serious' },
  pending: { label: 'W toku', tone: 'muted' },
};

export const STRENGTH: Record<EvidenceStrength, string> = {
  strong: 'Silna',
  moderate: 'Umiarkowana',
  weak: 'Słaba',
  none: 'Brak',
  unknown: '—',
};

export const INPUT_KIND: Record<InputKind, string> = { text: 'Tekst', url: 'Adres URL', image: 'Obraz' };

export const FLAG: Record<CheckFlag, { label: string; tone: Tone }> = {
  prompt_injection: { label: 'Prompt injection', tone: 'critical' },
  high_risk: { label: 'Wysokie ryzyko', tone: 'serious' },
  pii_masked: { label: 'Zamaskowano dane osobowe', tone: 'info' },
  archival_material: { label: 'Materiał archiwalny', tone: 'warning' },
  incident_match: { label: 'Znany incydent', tone: 'info' },
  source_status_warning: { label: 'Status źródła', tone: 'warning' },
  conflicting_sources: { label: 'Źródła sprzeczne', tone: 'warning' },
  no_evidence: { label: 'Brak danych', tone: 'neutral' },
  information_gap: { label: 'Luka informacyjna', tone: 'serious' },
  disinformation: { label: 'Możliwa dezinformacja', tone: 'critical' },
  refused: { label: 'Odrzucone', tone: 'serious' },
  user_report: { label: 'Zgłoszony błąd', tone: 'warning' },
};

export const REPORT_REASON: Record<string, string> = {
  wrong_verdict: 'Błędna ocena',
  bad_source: 'Złe lub niedziałające źródło',
  misunderstood: 'Źle zrozumiana treść',
  other: 'Inny powód',
};

export const ALERT_TYPE: Record<AlertType, { label: string; short: string }> = {
  information_gap: { label: 'Luka informacyjna', short: 'Luka' },
  query_surge: { label: 'Dużo zapytań o to samo', short: 'Wzrost' },
  high_risk: { label: 'Temat wysokiego ryzyka', short: 'Ryzyko' },
  prompt_injection: { label: 'Próby manipulacji (prompt injection)', short: 'Atak' },
  incident_match: { label: 'Znany incydent (kontekst)', short: 'Incydent' },
  source_status: { label: 'Status źródła', short: 'Źródło' },
  system: { label: 'Problem techniczny', short: 'System' },
  disinformation: { label: 'Możliwy atak dezinformacyjny', short: 'Dezinformacja' },
  dangerous_content: { label: 'Treści niebezpieczne', short: 'Treści' },
  known_disinformation: { label: 'Rosyjska dezinformacja (EUvsDisinfo)', short: 'EUvsDisinfo' },
  sql_injection: { label: 'Próby SQL injection', short: 'SQL' },
};

export const GAP_STATUS: Record<GapStatus, { label: string; tone: Tone }> = {
  suspected: { label: 'Podejrzenie', tone: 'muted' },
  active: { label: 'Aktywna', tone: 'serious' },
  in_progress: { label: 'W uzupełnianiu', tone: 'warning' },
  closed: { label: 'Zamknięta', tone: 'good' },
  rejected: { label: 'Odrzucona', tone: 'muted' },
};

/** Dangerous-content categories from backend/admin/safety.py. */
export const SAFETY_CATEGORY: Record<string, string> = {
  terroryzm: 'terroryzm',
  materialy_wybuchowe: 'materiały wybuchowe',
  bron: 'broń',
  bron_masowego_razenia: 'broń masowego rażenia',
  przemoc_masowa: 'przemoc masowa',
};

export const safetyLabel = (id: string) => SAFETY_CATEGORY[id] ?? id.replace(/_/g, ' ');

export const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  critical: { label: 'Krytyczny', tone: 'critical' },
  high: { label: 'Wysoki', tone: 'serious' },
  medium: { label: 'Średni', tone: 'warning' },
  low: { label: 'Niski', tone: 'neutral' },
};

export const ALERT_STATUS: Record<AlertStatus, { label: string; tone: Tone }> = {
  new: { label: 'Nowy', tone: 'info' },
  acknowledged: { label: 'Przyjęty', tone: 'neutral' },
  escalated: { label: 'W sprawie', tone: 'warning' },
  resolved: { label: 'Rozwiązany', tone: 'good' },
  dismissed: { label: 'Odrzucony', tone: 'muted' },
};

export const CASE_STATUS: Record<CaseStatus, { label: string; tone: Tone }> = {
  new: { label: 'Nowa', tone: 'info' },
  in_progress: { label: 'W toku', tone: 'warning' },
  waiting_for_source: { label: 'Oczekuje na źródło', tone: 'neutral' },
  resolved: { label: 'Rozwiązana', tone: 'good' },
  rejected: { label: 'Odrzucona', tone: 'muted' },
};

export const SOURCE_TYPE: Record<SourceType, string> = {
  official: 'Urzędowe',
  public_data: 'Dane publiczne',
  legal: 'Akty prawne',
  fact_check: 'Fact-checking',
  incident_db: 'Baza incydentów',
  media: 'Media',
  international: 'Organizacje międzynarodowe',
};

export const SOURCE_STATUS: Record<SourceStatus, { label: string; tone: Tone }> = {
  active: { label: 'Aktywne', tone: 'good' },
  suspended: { label: 'Zawieszone', tone: 'warning' },
  excluded: { label: 'Wykluczone', tone: 'muted' },
};

export const TIER: Record<'A' | 'B' | 'C', string> = {
  A: 'A — pierwotne / urzędowe',
  B: 'B — wiarygodne wtórne',
  C: 'C — tylko kontekst',
};

export const PIPELINE_ROLE: Record<PipelineRole, { label: string; description: string }> = {
  claim_extraction: {
    label: 'Rozpoznawanie twierdzeń',
    description: 'Wyodrębnia z wiadomości twierdzenia do sprawdzenia i słowa kluczowe.',
  },
  answer_generation: {
    label: 'Formułowanie odpowiedzi',
    description: 'Porównuje znalezione materiały z twierdzeniem i pisze uzasadnienie prostym językiem.',
  },
  embedding: {
    label: 'Wyszukiwanie semantyczne',
    description: 'Wektory do wyszukiwania w katalogu źródeł i grupowania podobnych zapytań.',
  },
  ocr: { label: 'OCR (tekst z obrazu)', description: 'Odczytuje tekst i daty ze zrzutów ekranu.' },
  transcription: { label: 'Transkrypcja', description: 'Zamienia nagrania głosowe na tekst.' },
  reverse_image: {
    label: 'Wcześniejsze wystąpienia obrazu',
    description: 'Szuka tego samego obrazu w lokalnym indeksie (kontekst czasu i miejsca).',
  },
};

export const REGION: Record<ProcessingRegion, { label: string; tone: Tone }> = {
  PL: { label: 'Polska', tone: 'good' },
  EOG: { label: 'EOG', tone: 'good' },
  poza_EOG: { label: 'Poza EOG', tone: 'warning' },
  self_hosted: { label: 'Własna infrastruktura', tone: 'good' },
};

export const PROTOCOL: Record<ProviderProtocol, string> = {
  openai_compatible: 'API zgodne z OpenAI',
  anthropic: 'Anthropic Messages API',
  google: 'Google Gemini API',
  ollama: 'Ollama',
  http_custom: 'Własny adapter HTTP',
};

export const HEALTH: Record<Health, { label: string; tone: Tone }> = {
  ok: { label: 'Działa', tone: 'good' },
  degraded: { label: 'Problemy', tone: 'warning' },
  down: { label: 'Niedostępny', tone: 'critical' },
  unknown: { label: 'Nie sprawdzono', tone: 'muted' },
};

export const SECURITY_TYPE: Record<SecurityEvent['type'], string> = {
  prompt_injection: 'Prompt injection',
  rate_limited: 'Limit zapytań',
  ssrf_blocked: 'Zablokowany adres (SSRF)',
  invalid_input: 'Nieprawidłowe wejście',
  auth_failed: 'Nieudane logowanie',
};

export const SECURITY_ACTION: Record<SecurityEvent['action'], string> = {
  instructions_ignored: 'Instrukcje zignorowane',
  blocked: 'Zablokowano',
  throttled: 'Spowolniono',
  logged: 'Zapisano',
};

export const CHANNEL_LABEL: Record<string, string> = {
  web: 'WWW',
  whatsapp: 'WhatsApp',
  sms: 'SMS',
  panel: 'Panel',
  api: 'API',
};

export const channelLabel = (id: string) => CHANNEL_LABEL[id] ?? id;
