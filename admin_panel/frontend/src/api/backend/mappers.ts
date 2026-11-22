/**
 * Translation between `backend/admin` (Polish vocabulary, snake_case) and the
 * panel's domain types. Keep every backend-specific word here so pages stay
 * independent of the data source.
 */
import { safetyLabel } from '../../components/labels.ts';
import { fmtDateTime, plural } from '../../utils/format.ts';
import type {
  Alert,
  AlertOccurrence,
  AlertStatus,
  AlertType,
  AuditEntry,
  CheckFlag,
  CheckOutcome,
  CheckRecord,
  ClaimResult,
  GapStatus,
  InputKind,
  MonitoringSettings,
  QueryCluster,
  RuntimeConfig,
  SecretName,
  Severity,
  TechEvent,
  ThreatReport,
  IpBlock,
  TrustedSite,
  User,
  Verdict,
} from '../types.ts';
import type {
  RawAccount,
  RawActivity,
  RawAlert,
  RawAudit,
  RawClaim,
  RawConfig,
  RawEvent,
  RawGap,
  RawQuery,
  RawSourceStatus,
  RawTopic,
  RawTrustedSource,
} from './raw.ts';

const HOUR = 3_600_000;

// ── verdicts and outcomes ───────────────────────────────────────────────────

/** Every verdict word the pipelines write (analysis/, whatsappAdapter, admin monitor). */
const VERDICT_FROM_BACKEND: Record<string, Verdict> = {
  prawda: 'confirmed',
  prawdziwy: 'confirmed',
  potwierdzony: 'confirmed',
  falsz: 'false',
  falszywy: 'false',
  zawiera_falsz: 'false',
  czesciowo_potwierdzony: 'misleading',
  sprzeczne_zrodla: 'misleading',
  manipulacja: 'misleading',
  brak_wystarczajacych_danych: 'insufficient',
  brak_danych: 'insufficient',
  nieweryfikowalny: 'not_verifiable',
};

/** Verdict filter → the value stored by the backend (the most common spelling). */
export const VERDICT_TO_BACKEND: Record<Verdict, string> = {
  confirmed: 'prawda',
  false: 'falsz',
  misleading: 'czesciowo_potwierdzony',
  insufficient: 'brak_wystarczajacych_danych',
  not_verifiable: 'nieweryfikowalny',
};

const ABSTAINING: ReadonlySet<Verdict> = new Set<Verdict>(['insufficient', 'not_verifiable']);
const TECHNICAL_VERDICTS = new Set(['blad_analizy']);

export function mapVerdict(value: string | null | undefined): Verdict | null {
  return value ? (VERDICT_FROM_BACKEND[value] ?? null) : null;
}

export function outcomeOf(q: Pick<RawQuery, 'status' | 'verdict'>): CheckOutcome {
  if (q.status === 'odrzucone') return 'refused';
  if (q.status === 'w_toku') return 'pending';
  if (q.status === 'blad' || (q.verdict && TECHNICAL_VERDICTS.has(q.verdict))) return 'technical_error';
  const verdict = mapVerdict(q.verdict);
  // No verdict after a finished check = no sources found (counted as a gap by the monitor).
  return verdict && !ABSTAINING.has(verdict) ? 'verdict' : 'abstained';
}

/** Outcome filter → `status` / `verdict` query parameters. */
export function outcomeFilter(outcome: CheckOutcome): Record<string, string> {
  switch (outcome) {
    case 'refused':
      return { status: 'odrzucone' };
    case 'pending':
      return { status: 'w_toku' };
    case 'technical_error':
      return { status: 'blad' };
    case 'abstained':
      return { verdict: 'brak_wystarczajacych_danych' };
    default:
      return { status: 'zakonczone' };
  }
}

// ── flags ───────────────────────────────────────────────────────────────────

/** Panel flag → prefix of the backend flag (the API matches `flag%`). */
export const FLAG_TO_BACKEND: Partial<Record<CheckFlag, string>> = {
  high_risk: 'niebezpieczne',
  refused: 'odrzucone',
  no_evidence: 'brak_danych',
  information_gap: 'luka_informacyjna',
  disinformation: 'kampania_dezinformacyjna',
  user_report: 'zgloszenie',
  prompt_injection: 'prompt_injection',
};

export const BACKEND_FLAGS = Object.keys(FLAG_TO_BACKEND) as CheckFlag[];

function mapFlags(flags: string[] | null): CheckFlag[] {
  const out = new Set<CheckFlag>();
  for (const flag of flags ?? []) {
    for (const [panel, prefix] of Object.entries(FLAG_TO_BACKEND)) {
      if (flag === prefix || flag.startsWith(`${prefix}:`)) out.add(panel as CheckFlag);
    }
  }
  return [...out];
}

const REFUSAL: Record<string, string> = {
  ip_zablokowany: 'Adres zablokowany po próbie prompt injection — zapytanie nie zostało sprawdzone.',
  niebezpieczna_tresc:
    'Prośba o instrukcje lub zdobycie broni, materiałów wybuchowych albo przemocy — odrzucona bez sprawdzania.',
};

function refusalReason(flags: string[] | null): string | undefined {
  const flag = (flags ?? []).find((f) => f.startsWith('odrzucone:'));
  if (!flag) return undefined;
  const reason = flag.slice('odrzucone:'.length);
  return REFUSAL[reason] ?? reason.replace(/_/g, ' ');
}

// ── queries (verification log) ──────────────────────────────────────────────

function durationMs(start: string, end: string | null): number {
  if (!end) return 0;
  const ms = Date.parse(end) - Date.parse(start);
  return Number.isFinite(ms) && ms > 0 ? ms : 0;
}

function inputKind(text: string): InputKind {
  return /^\s*https?:\/\/\S+\s*$/i.test(text) ? 'url' : 'text';
}

function mapClaim(claim: RawClaim, index: number): ClaimResult {
  const verdict = mapVerdict(claim.verdict);
  return {
    id: String(claim.id ?? index),
    text: claim.text,
    verdict,
    strength: claim.sources_count === 0 ? 'none' : 'unknown',
    rationale: '',
    evidence: [],
    missing:
      claim.kind === 'luka'
        ? 'Brak rozstrzygnięcia: nie znaleziono źródeł albo nie wystarczyły do oceny.'
        : claim.verdict && TECHNICAL_VERDICTS.has(claim.verdict)
          ? 'Błąd analizy źródeł — to nie jest werdykt.'
          : undefined,
    sourcesCount: claim.sources_count,
    topicId: claim.topic_id,
  };
}

export function mapQuery(q: RawQuery): CheckRecord {
  const text = q.text ?? '';
  const outcome = outcomeOf(q);
  return {
    id: q.id,
    createdAt: q.ts,
    channel: q.channel || 'api',
    inputKind: inputKind(text),
    query: text,
    outcome,
    overallVerdict: outcome === 'verdict' || outcome === 'abstained' ? mapVerdict(q.verdict) : null,
    strength: q.sources_count === 0 ? 'none' : 'unknown',
    claims: (q.claims ?? []).map(mapClaim),
    flags: mapFlags(q.flags),
    riskTopics: (q.safety?.categories ?? []).map(safetyLabel),
    durationMs: durationMs(q.ts, q.completed_at),
    models: {},
    tokens: 0,
    costPln: 0,
    errorMessage: outcome === 'refused' ? refusalReason(q.flags) : (q.error ?? undefined),
    sourcesCount: q.sources_count,
    requestId: q.request_id,
    report: q.report ? { reason: q.report.reason, comment: q.report.comment ?? null, at: q.report.ts ?? null } : null,
  };
}

// ── alerts ──────────────────────────────────────────────────────────────────

const ALERT_TYPE_FROM_BACKEND: Record<string, AlertType> = {
  luka_informacyjna: 'information_gap',
  kampania_dezinformacyjna: 'disinformation',
  tresci_niebezpieczne: 'dangerous_content',
  prompt_injection: 'prompt_injection',
  rosyjska_dezinformacja: 'known_disinformation',
  sql_injection: 'sql_injection',
};

export const ALERT_TYPE_TO_BACKEND: Partial<Record<AlertType, string>> = Object.fromEntries(
  Object.entries(ALERT_TYPE_FROM_BACKEND).map(([k, v]) => [v, k]),
);

export const BACKEND_ALERT_TYPES = Object.values(ALERT_TYPE_FROM_BACKEND);

const SEVERITY_FROM_BACKEND: Record<string, Severity> = {
  krytyczna: 'critical',
  wysoka: 'high',
  srednia: 'medium',
  niska: 'low',
};

const ALERT_STATUS_FROM_BACKEND: Record<string, AlertStatus> = {
  otwarty: 'new',
  w_analizie: 'acknowledged',
  rozwiazany: 'resolved',
  falszywy_alarm: 'dismissed',
};

export const ALERT_STATUS_TO_BACKEND: Record<AlertStatus, string> = {
  new: 'otwarty',
  acknowledged: 'w_analizie',
  escalated: 'w_analizie',
  resolved: 'rozwiazany',
  dismissed: 'falszywy_alarm',
};

const queries = (n: number) => `${n} ${plural(n, ['zapytanie', 'zapytania', 'zapytań'])}`;
/** „od 1 zapytania”, „od 3 zapytań” (dopełniacz). */
const fromQueries = (n: number) => `${n} ${n === 1 ? 'zapytania' : 'zapytań'}`;
const num = (value: unknown): number => (typeof value === 'number' ? value : Number(value) || 0);
const text = (value: unknown): string => (typeof value === 'string' ? value : '');

function categoryList(raw: unknown): string[] {
  return Object.entries((raw as Record<string, number> | undefined) ?? {})
    .sort((x, y) => y[1] - x[1])
    .map(([name, n]) => `${safetyLabel(name)} (${n})`);
}

const CHANNEL_NAME: Record<string, string> = { web: 'strona WWW', whatsapp: 'WhatsApp', panel: 'panel', test: 'test' };

/** Adres po prompt injection (``ip_blocks``, w alertach ``details.blokada``). */
export function mapIpBlock(raw: Record<string, unknown>): IpBlock {
  const str = (v: unknown) => (typeof v === 'string' && v ? v : null);
  return {
    key: String(raw.ip_key ?? ''),
    label: String(raw.label ?? 'adres'),
    attempts: num(raw.attempts),
    firstSeen: str(raw.first_seen),
    lastSeen: str(raw.last_seen),
    blockedUntil: str(raw.blocked_until),
    blockedBy: str(raw.blocked_by),
    reason: str(raw.reason),
    active: raw.active === true,
    permanent: raw.permanent === true,
    alertId: str(raw.alert_id),
  };
}

/** Ostatnie wystąpienia alertów-zdarzeń (``details.wystapienia``), najnowsze pierwsze. */
function occurrencesOf(a: RawAlert, type: AlertType): AlertOccurrence[] {
  const list = Array.isArray(a.details?.wystapienia) ? (a.details.wystapienia as Record<string, unknown>[]) : [];
  return list.slice(0, 10).map((o) => {
    const channel = text(o.kanal);
    if (type === 'prompt_injection') {
      return {
        at: text(o.ts),
        text: text(o.fragment) ? `„${text(o.fragment)}”` : 'polecenie dla modelu w treści zapytania',
        detail: [CHANNEL_NAME[channel] ?? channel, o.zablokowany === true ? 'odrzucone — adres zablokowany' : '']
          .filter(Boolean)
          .join(' · '),
        queryId: text(o.query_id) || undefined,
      };
    }
    if (type === 'sql_injection') {
      const fields = Array.isArray(o.pola) ? (o.pola as string[]).join(', ') : '';
      const patterns = Array.isArray(o.wzorce) ? (o.wzorce as string[]).join(', ') : '';
      return {
        at: text(o.ts),
        text: [text(o.metoda), text(o.sciezka)].filter(Boolean).join(' ') || 'treść wiadomości',
        detail: [fields && `pola: ${fields}`, patterns && `wzorce: ${patterns}`].filter(Boolean).join(' · '),
        queryId: text(o.query_id) || undefined,
      };
    }
    return {
      at: text(o.ts),
      text: text(o.twierdzenie) || 'twierdzenie z zapytania',
      detail: [channel && `kanał: ${channel}`, text(o.uzasadnienie)].filter(Boolean).join(' · '),
      queryId: text(o.query_id) || undefined,
    };
  });
}

function describeAlert(a: RawAlert, type: AlertType, m: MonitoringSettings | null) {
  const d = a.details ?? {};
  const windowH = num(d.okno_h);
  const metrics: Record<string, string | number> = {};
  let description: string;
  let rule: string;

  switch (type) {
    case 'dangerous_content': {
      const high = num(d.wysokie_ryzyko);
      const categories = categoryList(d.kategorie);
      description =
        `W ciągu ${windowH} h przyszło ${queries(a.count)} o treści niebezpieczne (terroryzm, broń, ` +
        `materiały wybuchowe…)` +
        (high ? `, w tym ${high} wysokiego ryzyka — prośby o instrukcje lub zdobycie, odrzucone bez sprawdzania` : '') +
        '. Alert jest zbiorczy: nie zbieramy danych o tym, kto pyta.';
      rule = m
        ? `alert od ${fromQueries(m.dangerous_alert_after)} w ${m.dangerous_window_hours} h; ` +
          (m.refuse_high_risk ? 'prośby o instrukcje są odrzucane' : 'odrzucanie próśb o instrukcje wyłączone')
        : 'wiele zapytań o treści niebezpieczne w krótkim czasie';
      metrics['Zapytania'] = a.count;
      metrics['Wysokiego ryzyka'] = high;
      if (categories.length) metrics['Kategorie'] = categories.join(', ');
      break;
    }
    case 'prompt_injection': {
      const address = text(d.adres);
      const channel = text(d.kanal);
      const tries = `${a.count} ${plural(a.count, ['próba', 'próby', 'prób'])}`;
      description = address
        ? `Z adresu ${address} ${plural(a.count, ['przyszła', 'przyszły', 'przyszło'])} ${tries} sterowania modelem (prompt injection): polecenia ` +
          'w treści zapytania, np. „zignoruj poprzednie instrukcje”. Każda próba jest oznaczona w historii weryfikacji.'
        : windowH
          ? `W ciągu ${windowH} h wykryto ${queries(a.count)} z poleceniami dla modelu (prompt injection).`
          : `Kanał ${CHANNEL_NAME[channel] ?? channel}: ${tries} sterowania modelem (prompt injection). ` +
            'Bez adresu IP (np. WhatsApp) nie ma blokady — treść jest sprawdzana jako dane, polecenia są ignorowane.';
      rule = m
        ? m.injection_block_ip
          ? `blokada adresu IP po ${m.injection_block_after} ${m.injection_block_after === 1 ? 'próbie' : 'próbach'} w ` +
            `${m.dangerous_window_hours} h, na ${m.injection_block_hours} h`
          : 'automatyczna blokada adresów wyłączona — tylko oznaczenie i alert'
        : 'każda próba sterowania modelem';
      metrics['Próby'] = a.count;
      if (address) metrics['Adres'] = address;
      if (channel) metrics['Kanał'] = CHANNEL_NAME[channel] ?? channel;
      break;
    }
    case 'disinformation':
      description =
        `W ciągu ${windowH} h ${queries(a.count)} dotyczyło twierdzenia ocenionego jako fałsz. ` +
        'Może to być skoordynowane rozpowszechnianie dezinformacji.';
      rule = m
        ? `≥ ${queries(m.disinfo_min_users)} w ${m.disinfo_window_hours} h o twierdzenie ocenione jako fałsz; ` +
          `od ${fromQueries(2 * m.disinfo_min_users)} — wysoki priorytet`
        : 'wiele zapytań o twierdzenie ocenione jako fałsz';
      metrics['Zapytania'] = a.count;
      break;
    case 'known_disinformation': {
      const caseInfo = (d.przypadek ?? {}) as Record<string, unknown>;
      description =
        text(d.opis) ||
        'Zapytano o twierdzenie, które baza EUvsDisinfo dokumentuje jako prokremlowską dezinformację.';
      rule = `twierdzenie znalezione w bazie ${text(d.zrodlo) || 'EUvsDisinfo'}; każde kolejne zapytanie zwiększa licznik`;
      metrics['Zapytania'] = a.count;
      if (text(caseInfo.tytul)) metrics['Przypadek w bazie'] = text(caseInfo.tytul);
      break;
    }
    case 'sql_injection':
      description =
        text(d.opis) ||
        'Wykryto składnię SQL injection w danych wejściowych. Zapytania do bazy są parametryzowane, więc nic nie zostało wykonane.';
      rule = `każda próba na kanale ${text(d.kanal) || '—'} zwiększa licznik; w alercie nie ma wartości pól ani adresu nadawcy`;
      metrics['Próby'] = a.count;
      if (text(d.kanal)) metrics['Kanał'] = text(d.kanal);
      break;
    default:
      description =
        `O temat, którego system nie rozstrzygnął (brak źródeł albo niewystarczające dane), ` +
        `zapytano ${a.count} ${plural(a.count, ['raz', 'razy', 'razy'])} w oknie ${windowH} h.`;
      rule = m
        ? `≥ ${queries(m.info_gap_min_queries)} w ${m.info_gap_window_hours} h o temat bez rozstrzygnięcia; ` +
          `od ${fromQueries(3 * m.info_gap_min_queries)} — wysoki priorytet`
        : 'kilka zapytań o temat bez rozstrzygnięcia';
      metrics['Zapytania bez dowodów'] = a.count;
  }
  if (windowH) metrics['Okno'] = `${windowH} h`;
  metrics['Pierwsze zgłoszenie'] = fmtDateTime(a.first_seen);
  return { description, rule, metrics };
}

export function mapAlert(a: RawAlert, monitoring: MonitoringSettings | null): Alert {
  const type = ALERT_TYPE_FROM_BACKEND[a.type] ?? 'system';
  const { description, rule, metrics } = describeAlert(a, type, monitoring);
  const aboutTopic = type === 'information_gap' || type === 'disinformation';
  const caseInfo = (a.details?.przypadek ?? {}) as Record<string, unknown>;
  return {
    id: a.id,
    type,
    severity: SEVERITY_FROM_BACKEND[a.severity] ?? 'medium',
    status: ALERT_STATUS_FROM_BACKEND[a.status] ?? 'new',
    title: a.title,
    description,
    rule,
    createdAt: a.first_seen,
    updatedAt: a.last_seen,
    clusterId: aboutTopic ? a.subject : undefined,
    checkIds: [],
    queryCount: a.count,
    metrics,
    notified: [],
    note: a.note ?? undefined,
    occurrences: occurrencesOf(a, type),
    ipBlock:
      a.details?.blokada && typeof a.details.blokada === 'object'
        ? mapIpBlock(a.details.blokada as Record<string, unknown>)
        : undefined,
    link: text(caseInfo.url) ? { label: 'Przypadek w bazie EUvsDisinfo', url: text(caseInfo.url) } : undefined,
  };
}

// ── topics and information gaps ─────────────────────────────────────────────

const GAP_FROM_BACKEND: Record<string, GapStatus> = {
  podejrzenie: 'suspected',
  aktywna: 'active',
  w_uzupelnianiu: 'in_progress',
  zamknieta: 'closed',
  odrzucona: 'rejected',
};

export const GAP_TO_BACKEND: Record<GapStatus, string> = {
  suspected: 'podejrzenie',
  active: 'aktywna',
  in_progress: 'w_uzupelnianiu',
  closed: 'zamknieta',
  rejected: 'odrzucona',
};

export function mapTopic(gap: RawGap, topic: RawTopic | null, now = Date.now()): QueryCluster {
  const claims = topic?.claims ?? [];
  const byKind = topic?.by_kind ?? {};
  const counted = Object.values(byKind).reduce((s, k) => s + k.claims, 0);
  const total = counted || claims.length;
  const noEvidence = byKind.luka?.claims ?? claims.filter((c) => c.kind === 'luka').length;

  const hourly = new Array<number>(48).fill(0);
  let inWindow = 0;
  let previousWindow = 0;
  const verdicts: Partial<Record<Verdict, number>> = {};
  for (const claim of claims) {
    const age = now - Date.parse(claim.ts ?? '');
    if (Number.isFinite(age) && age >= 0) {
      const bucket = 47 - Math.floor(age / HOUR);
      if (bucket >= 0) hourly[bucket] += 1;
      if (age < 24 * HOUR) inWindow += 1;
      else if (age < 48 * HOUR) previousWindow += 1;
    }
    const verdict = mapVerdict(claim.verdict) ?? (claim.kind === 'luka' ? 'insufficient' : null);
    if (verdict) verdicts[verdict] = (verdicts[verdict] ?? 0) + 1;
  }

  const status = GAP_FROM_BACKEND[gap.gap_status];
  return {
    id: gap.id,
    label: gap.label,
    keywords: (topic?.tokens ?? []).slice(0, 6),
    total,
    inWindow,
    previousWindow,
    // Anonymous: the backend counts queries, not people.
    uniqueSessions: gap.gap_queries ?? total,
    noEvidence,
    noEvidenceRatio: total ? noEvidence / total : 0,
    verdicts,
    channels: {},
    firstSeen: gap.created_at,
    lastSeen: gap.last_seen,
    hourly,
    riskTopics: [],
    sampleQueries: [...new Set(claims.map((c) => c.text))].slice(0, 6),
    isInformationGap: status === 'active' || status === 'in_progress',
    isSurging: false,
    gapStatus: status,
    gapNote: gap.gap_note ?? undefined,
    gapSince: gap.gap_since ?? undefined,
    gapUpdatedAt: gap.gap_updated_at ?? undefined,
  };
}

// ── configuration and audit ─────────────────────────────────────────────────

export function mapConfig(raw: RawConfig, previous?: RuntimeConfig): RuntimeConfig {
  const secrets = Object.fromEntries(
    Object.entries(raw.secrets ?? {}).map(([name, s]) => [
      name,
      { overridden: s.nadpisany, set: s.ustawiony, mask: s.maska },
    ]),
  ) as RuntimeConfig['secrets'];
  return {
    llm: raw.llm,
    apis: raw.apis,
    monitoring: raw.monitoring,
    secrets,
    effective: raw.efektywne ?? {},
    apiClients: raw.api_clients ?? previous?.apiClients ?? [],
    file: raw.file ?? previous?.file ?? '',
  };
}

export const SECRET_LABEL: Record<SecretName, string> = {
  freellm_api_key: 'Klucz API modelu językowego (FREELLM_API_KEY)',
  google_fact_check_api_key: 'Google Fact Check Tools (GOOGLE_FACT_CHECK_API_KEY)',
  diffbot_api_token: 'Diffbot — pobieranie artykułów (DIFFBOT_API_TOKEN)',
};

const FIELD_LABEL: Record<string, string> = {
  'llm.model': 'Model główny',
  'llm.text_analysis_model': 'Model analizy tekstu',
  'llm.base_url': 'Adres API modelu',
  'llm.timeout_s': 'Limit czasu modelu',
  'llm.max_retries': 'Ponowienia modelu',
  'apis.disabled_clients': 'Wyłączone źródła danych',
  'apis.article_scraping_enabled': 'Pobieranie artykułów',
  'apis.article_extractor': 'Ekstraktor artykułów',
  'monitoring.retention_days': 'Retencja danych (dni)',
  'monitoring.info_gap_min_queries': 'Luka: zapytania',
  'monitoring.info_gap_window_hours': 'Luka: okno czasu (h)',
  'monitoring.disinfo_min_users': 'Dezinformacja: zapytania',
  'monitoring.disinfo_window_hours': 'Dezinformacja: okno czasu (h)',
  'monitoring.dangerous_alert_after': 'Treści niebezpieczne: alert po',
  'monitoring.dangerous_window_hours': 'Treści niebezpieczne: okno czasu (h)',
  'monitoring.injection_block_ip': 'Prompt injection: blokada adresu IP',
  'monitoring.injection_block_after': 'Prompt injection: blokada po (próbach)',
  'monitoring.injection_block_hours': 'Prompt injection: długość blokady (h)',
  'monitoring.refuse_high_risk': 'Odrzucanie treści wysokiego ryzyka',
};

export function fieldLabel(field: string): string {
  if (field.startsWith('konta.')) {
    const rest = field.slice('konta.'.length);
    for (const [suffix, label] of [['.rola', 'rola'], ['.aktywne', 'aktywne'], ['.nazwa', 'nazwa'], ['.haslo', 'hasło']]) {
      if (rest.endsWith(suffix)) return `Konto ${rest.slice(0, -suffix.length)}: ${label}`;
    }
    return `Nowe konto ${rest}`;
  }
  const [section, name] = field.split('.');
  if (FIELD_LABEL[field]) return FIELD_LABEL[field];
  if (section === 'secrets' && name in SECRET_LABEL) return SECRET_LABEL[name as SecretName];
  return field;
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'z .env';
  if (typeof value === 'boolean') return value ? 'tak' : 'nie';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '(brak)';
  return String(value);
}

export function mapAudit(row: RawAudit): AuditEntry {
  return {
    id: String(row.id),
    at: row.ts,
    actor: row.actor,
    action: row.field.startsWith('secrets.')
      ? 'Zmiana klucza API'
      : row.field.startsWith('konta.')
        ? 'Konta panelu'
        : 'Zmiana konfiguracji',
    target: `${fieldLabel(row.field)} (${row.field})`,
    detail: `${formatValue(row.old)} → ${formatValue(row.new)}`,
  };
}

// ── observability events ────────────────────────────────────────────────────

export function mapEvent(raw: RawEvent, index: number): TechEvent {
  const { ts, level, event, request_id, ...fields } = raw;
  return {
    id: `${index}-${ts ?? ''}`,
    at: ts ?? '',
    level: level ?? 'info',
    event: event ?? 'log',
    requestId: request_id,
    fields,
  };
}

// ── panel accounts ──────────────────────────────────────────────────────────

export function mapAccount(a: RawAccount): User {
  return {
    id: String(a.id),
    email: a.email,
    name: a.name,
    role: a.role,
    active: a.active,
    createdAt: a.createdAt,
    lastLoginAt: a.lastLoginAt ?? undefined,
  };
}

// ── activity log (activity_logs) ────────────────────────────────────────────

const ACTION_LABEL: Record<string, string> = {
  'auth.login': 'Logowanie',
  'auth.login_failed': 'Nieudane logowanie',
  'auth.logout': 'Wylogowanie',
  'auth.password_changed': 'Zmiana własnego hasła',
  'auth.password_reset': 'Ustawienie hasła przez administratora',
  'auth.token_created': 'Nowy token dostępu',
  'auth.token_revoked': 'Unieważnienie tokenu',
  'user.created': 'Nowe konto',
  'user.updated': 'Zmiana konta',
  'user.deleted': 'Usunięcie konta',
  'config.updated': 'Zmiana konfiguracji',
  'alert.status_changed': 'Zmiana statusu alertu',
  'info_gap.status_changed': 'Zmiana stanu luki informacyjnej',
  'maintenance.purged': 'Usunięcie starych danych',
  'ip.blocked': 'Blokada adresu IP (prompt injection)',
  'ip.unblocked': 'Odblokowanie adresu IP',
  'source.created': 'Nowe źródło zaufane',
  'source.updated': 'Zmiana źródła zaufanego',
  'source.deleted': 'Usunięcie źródła zaufanego',
  'source.seeded': 'Wgranie listy źródeł',
};

const SUBJECT_LABEL: Record<string, string> = {
  user: 'konto',
  alert: 'alert',
  topic: 'temat',
  config: 'konfiguracja',
  ip: 'adres IP',
  source: 'źródło',
  token: 'token',
};

function activityDetail(details: Record<string, unknown> | null): string {
  if (!details) return '';
  const changes = details.changes;
  if (Array.isArray(changes)) {
    return changes
      .map((c) => {
        const change = c as { field?: string; old?: unknown; new?: unknown };
        return `${fieldLabel(change.field ?? '')}: ${formatValue(change.old)} → ${formatValue(change.new)}`;
      })
      .join('; ');
  }
  return Object.entries(details)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(', ');
}

export function mapActivity(row: RawActivity): AuditEntry {
  const subject = row.subject_type ? `${SUBJECT_LABEL[row.subject_type] ?? row.subject_type} ${row.subject_id ?? ''}`.trim() : '—';
  const detail = activityDetail(row.details);
  return {
    id: String(row.id),
    at: row.occurred_at,
    actor: row.actor,
    action: ACTION_LABEL[row.action] ?? row.action,
    target: subject,
    detail: [detail, row.ip_address ? `IP ${row.ip_address}` : ''].filter(Boolean).join(' · '),
  };
}

// ── trusted sites ───────────────────────────────────────────────────────────

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Same URL for the table and the registry (the registry drops `#…` and lowercases the host). */
function siteKey(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.hash = '';
    return parsed.toString();
  } catch {
    return url;
  }
}

/** A `trusted_sources` row joined with what the running verification knows about it. */
export function mapTrustedSite(row: RawTrustedSource, status?: RawSourceStatus): TrustedSite {
  return {
    url: row.url,
    name: row.name,
    domain: hostOf(row.url),
    topics: row.topics ?? [],
    description: row.description ?? '',
    enabled: row.enabled,
    adapter: row.adapter ?? (status && status.adapter !== 'pending' ? status.adapter : null),
    adapterLocked: !!row.adapter,
    trust: status?.trust ?? null,
    lastCheck: status?.last_check ?? null,
    loaded: !!status,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export function joinTrustedSites(rows: RawTrustedSource[], statuses: RawSourceStatus[]): TrustedSite[] {
  const byUrl = new Map(statuses.map((s) => [siteKey(s.url), s]));
  return rows.map((row) => mapTrustedSite(row, byUrl.get(siteKey(row.url))));
}

// ── threats ─────────────────────────────────────────────────────────────────

type RawRecord = Record<string, unknown>;
const str = (v: unknown): string | null => (v === null || v === undefined || v === '' ? null : String(v));
const records = (v: unknown): RawRecord[] => (Array.isArray(v) ? (v as RawRecord[]) : []);
const counts = (v: unknown): Record<string, number> => (v && typeof v === 'object' ? (v as Record<string, number>) : {});

function subject(raw: RawRecord) {
  return {
    channel: str(raw.channel),
    queryId: str(raw.query_id),
    text: str(raw.text),
  };
}

/** `GET /threats` → panel types (snake_case → camelCase, defensive about missing fields). */
export function mapThreats(raw: RawRecord): ThreatReport {
  const summary = (raw.summary ?? {}) as RawRecord;
  const injection = (raw.prompt_injection ?? {}) as RawRecord;
  const manipulation = (raw.manipulation ?? {}) as RawRecord;
  const critical = (raw.critical ?? {}) as RawRecord;
  return {
    file: String(raw.file ?? ''),
    logAvailable: raw.log_available !== false,
    since: String(raw.since ?? ''),
    until: String(raw.until ?? ''),
    hours: num(raw.hours),
    eventsScanned: num(raw.events_scanned),
    summary: {
      promptInjection: num(summary.prompt_injection),
      manipulationCampaigns: num(summary.manipulation_campaigns),
      criticalQueries: num(summary.critical_queries),
      refused: num(summary.refused),
    },
    timeline: records(raw.timeline).map((b) => ({
      bucket: String(b.bucket),
      promptInjection: num(b.prompt_injection),
      manipulation: num(b.manipulation),
      critical: num(b.critical),
    })),
    injection: {
      bySource: counts(injection.by_source),
      byDetector: counts(injection.by_detector),
      repeatedTexts: num(injection.repeated_texts),
      recent: records(injection.recent).map((e) => ({
        ...subject(e),
        at: String(e.ts),
        requestId: str(e.request_id),
        source: str(e.source),
        kind: str(e.kind),
        detector: str(e.detector),
        pattern: str(e.pattern),
        snippet: str(e.snippet),
        repeats: num(e.repeats) || 1,
      })),
    },
    campaigns: records(manipulation.campaigns).map((c) => ({
      alertId: str(c.alert_id),
      title: String(c.title ?? 'Możliwy atak dezinformacyjny'),
      claim: str(c.claim),
      topicId: str(c.topic_id),
      status: str(c.status),
      severity: str(c.severity),
      count: c.count === null || c.count === undefined ? null : num(c.count),
      signals: num(c.signals),
      firstSignal: String(c.first_signal),
      lastSignal: String(c.last_signal),
    })),
    critical: {
      byCategory: counts(critical.by_category),
      bySeverity: counts(critical.by_severity),
      recent: records(critical.recent).map((e) => ({
        ...subject(e),
        at: String(e.ts),
        refused: e.refused === true,
        reason: str(e.reason),
        severity: str(e.severity),
        categories: Array.isArray(e.categories) ? e.categories.map(String) : [],
        requestId: str(e.request_id),
      })),
    },
  };
}
