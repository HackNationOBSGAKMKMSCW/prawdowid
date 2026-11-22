/**
 * Domain types shared by every data source. The mock follows
 * `admin_panel/openapi.yaml`; the HTTP client maps the real backend
 * (`backend/admin`) onto the same types in `api/backend/mappers.ts`.
 * Types that exist only in the real backend are at the end of this file.
 */

export type ISODate = string;

// ── Users and sessions ──────────────────────────────────────────────────────

/** `user` = account of the public service (no panel access); the rest are panel roles. */
// The moderator role is switched off for now: the panel has administrators and analysts.
export type Role = 'admin' | 'analyst' | 'user';

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  active: boolean;
  createdAt: ISODate;
  lastLoginAt?: ISODate;
}

export interface Session {
  token: string;
  user: User;
  expiresAt: ISODate;
}

// ── Checks (the verification log) ───────────────────────────────────────────

/** The five result classes from the brief. */
export type Verdict = 'confirmed' | 'false' | 'misleading' | 'insufficient' | 'not_verifiable';

/**
 * How a check ended. Only `verdict` and `abstained` are substantive results:
 * a technical failure or a request for clarification is never a verdict.
 */
export type CheckOutcome =
  | 'verdict'
  | 'abstained'
  | 'technical_error'
  | 'needs_clarification'
  /** Not processed: blocked user or a high-risk request (backend/admin). */
  | 'refused'
  /** Still being checked. */
  | 'pending';

/** `unknown` = the data source does not report evidence strength. */
export type EvidenceStrength = 'strong' | 'moderate' | 'weak' | 'none' | 'unknown';

export type InputKind = 'text' | 'url' | 'image';

export type CheckFlag =
  | 'prompt_injection'
  | 'high_risk'
  | 'pii_masked'
  | 'archival_material'
  | 'incident_match'
  | 'source_status_warning'
  | 'conflicting_sources'
  | 'no_evidence'
  | 'information_gap'
  | 'disinformation'
  | 'refused'
  /** Someone reported a mistake in the result (`POST /api/check/{id}/report`). */
  | 'user_report';

export interface Evidence {
  id: string;
  sourceId: string;
  title: string;
  publisher: string;
  url: string;
  publishedAt?: ISODate;
  retrievedAt: ISODate;
  snippet?: string;
  stance: 'supports' | 'refutes' | 'context';
}

export interface ClaimResult {
  id: string;
  text: string;
  /** `null` = no verdict (e.g. analysis error). */
  verdict: Verdict | null;
  strength: EvidenceStrength;
  rationale: string;
  evidence: Evidence[];
  /** What could not be established — filled in when the system abstains. */
  missing?: string;
  /** Number of sources found, when the backend reports a count but not the items. */
  sourcesCount?: number | null;
  /** Topic (query cluster) the claim was grouped into. */
  topicId?: string;
}

export interface CheckRecord {
  id: string;
  createdAt: ISODate;
  channel: string;
  inputKind: InputKind;
  /** User input with personal data already masked by the backend. */
  query: string;
  outcome: CheckOutcome;
  overallVerdict: Verdict | null;
  strength: EvidenceStrength;
  claims: ClaimResult[];
  flags: CheckFlag[];
  riskTopics: string[];
  clusterId?: string;
  durationMs: number;
  /** Model used for each pipeline stage, e.g. { claim_extraction: "provider/model" }. */
  models: Partial<Record<PipelineRole, string>>;
  tokens: number;
  costPln: number;
  errorMessage?: string;
  /** Pseudonymised end user (HMAC) and their masked id, e.g. `***456`. */
  userKey?: string;
  userLabel?: string;
  sourcesCount?: number | null;
  requestId?: string | null;
  /** Mistake reported by the person who asked (website "Zgłoś błąd"). */
  report?: UserReport | null;
}

export interface UserReport {
  reason: 'wrong_verdict' | 'bad_source' | 'misunderstood' | 'other' | string;
  comment: string | null;
  at: ISODate | null;
}

export interface CheckQuery {
  search?: string;
  outcome?: CheckOutcome | 'any';
  verdict?: Verdict | 'any';
  channel?: string;
  flag?: CheckFlag | 'any';
  clusterId?: string;
  sinceHours?: number;
  page?: number;
  pageSize?: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

// ── Query clusters: repeated questions and information gaps ────────────────

export interface QueryCluster {
  id: string;
  /** Representative (masked) question of the group. */
  label: string;
  keywords: string[];
  total: number;
  /** Queries in the current detection window. */
  inWindow: number;
  /** Queries in the window before it — the baseline for surge detection. */
  previousWindow: number;
  uniqueSessions: number;
  /** Queries in the information-gap window that ended without enough evidence. */
  noEvidence: number;
  /** `noEvidence` as a share of all queries in the information-gap window (0–1). */
  noEvidenceRatio: number;
  verdicts: Partial<Record<Verdict, number>>;
  channels: Record<string, number>;
  firstSeen: ISODate;
  lastSeen: ISODate;
  /** Query counts per hour for the last 48 hours, oldest first. */
  hourly: number[];
  riskTopics: string[];
  sampleQueries: string[];
  /** What the system could not establish (for information gaps). */
  missing?: string;
  isInformationGap: boolean;
  isSurging: boolean;
  caseId?: string;
  /** Information-gap lifecycle, when the backend manages it (backend/admin). */
  gapStatus?: GapStatus;
  gapNote?: string;
  gapSince?: ISODate;
  gapUpdatedAt?: ISODate;
}

export interface ClusterQuery {
  onlyGaps?: boolean;
  onlySurging?: boolean;
  search?: string;
  /** Counts only: the source may skip per-cluster details (series, samples). */
  light?: boolean;
}

// ── Alerts and warnings ─────────────────────────────────────────────────────

export type AlertType =
  | 'information_gap'
  | 'query_surge'
  | 'high_risk'
  | 'prompt_injection'
  | 'incident_match'
  | 'source_status'
  | 'system'
  /** Many different people ask about a claim rated false (backend/admin). */
  | 'disinformation'
  /** One user repeatedly asks for dangerous content (backend/admin). */
  | 'dangerous_user';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type AlertStatus = 'new' | 'acknowledged' | 'escalated' | 'resolved' | 'dismissed';

export interface UserRef {
  id: string;
  name: string;
  role: Role;
}

export interface Notification {
  user: UserRef;
  channel: 'panel' | 'email';
  at: ISODate;
}

export interface Alert {
  id: string;
  type: AlertType;
  severity: Severity;
  status: AlertStatus;
  title: string;
  description: string;
  /** Human-readable rule that fired, e.g. "≥ 5 zapytań bez dowodów w 24 h". */
  rule: string;
  createdAt: ISODate;
  updatedAt: ISODate;
  clusterId?: string;
  caseId?: string;
  checkIds: string[];
  metrics: Record<string, string | number>;
  /** Recipients actually notified (sent), as opposed to recommendations. */
  notified: Notification[];
  /** Role the rules recommend notifying when nobody is assigned to the alert type. */
  recommendedRole?: Role;
  /** Number of related queries when the backend reports a count instead of ids. */
  queryCount?: number;
  /** End user the alert is about (`dangerous_user`). */
  userKey?: string;
  /** Admin's note from the last status change. */
  note?: string;
}

export interface AlertQuery {
  type?: AlertType | 'any';
  severity?: Severity | 'any';
  status?: AlertStatus | 'any' | 'open';
}

// ── Moderator cases (closed information loop) ──────────────────────────────

export type CaseStatus = 'new' | 'in_progress' | 'waiting_for_source' | 'resolved' | 'rejected';

export type CaseEventKind =
  | 'created'
  | 'status_changed'
  | 'comment'
  | 'queries_linked'
  | 'assigned'
  | 'forward_recommended'
  | 'forwarded';

export interface CaseEvent {
  id: string;
  at: ISODate;
  actor: string;
  kind: CaseEventKind;
  text: string;
}

export interface CaseForwarding {
  /** The system recommends handing the case over — nothing has been sent yet. */
  recommended: boolean;
  recommendedRole?: Role;
  reason?: string;
  /** Set only when the case was actually handed over to a person. */
  forwardedTo?: UserRef;
  forwardedAt?: ISODate;
  forwardedBy?: string;
}

export interface ModeratorCase {
  id: string;
  title: string;
  status: CaseStatus;
  priority: Severity;
  clusterId?: string;
  alertIds: string[];
  checkIds: string[];
  queryCount: number;
  assignee?: UserRef;
  forwarding: CaseForwarding;
  riskTopics: string[];
  createdAt: ISODate;
  updatedAt: ISODate;
  resolution?: string;
  events: CaseEvent[];
}

export interface CaseQuery {
  status?: CaseStatus | 'open' | 'any';
  search?: string;
}

export interface CasePatch {
  status?: CaseStatus;
  assigneeId?: string | null;
  priority?: Severity;
  resolution?: string;
}

// ── Source catalogue ────────────────────────────────────────────────────────

export type SourceType =
  | 'official'
  | 'public_data'
  | 'legal'
  | 'fact_check'
  | 'incident_db'
  | 'media'
  | 'international';

export type SourceStatus = 'active' | 'suspended' | 'excluded';

export interface Source {
  id: string;
  name: string;
  url: string;
  domain: string;
  type: SourceType;
  /** A = primary / official, B = verified secondary, C = context only. */
  tier: 'A' | 'B' | 'C';
  language: string;
  license: string;
  status: SourceStatus;
  documents: number;
  updateFrequency: string;
  qualification: string;
  statusNote?: string;
  addedAt: ISODate;
  lastFetchedAt?: ISODate;
  lastFetchOk: boolean;
}

export type SourceInput = Pick<
  Source,
  'name' | 'url' | 'type' | 'tier' | 'language' | 'license' | 'updateFrequency' | 'qualification'
>;

/** A site the verification searches (backend: `trusted_sources`, key = URL). */
export interface TrustedSite {
  url: string;
  name: string;
  domain: string;
  topics: string[];
  description: string;
  enabled: boolean;
  /** How the site is searched (`govpl_search`, `fact_check_publisher`, …); null = not detected yet. */
  adapter: string | null;
  /** Set by hand in the table; automatic detection never overrides it. */
  adapterLocked: boolean;
  trust: 'official' | 'fact_checker' | string | null;
  lastCheck: { at: ISODate; ok: boolean; error: string | null } | null;
  /** False when the site is in the table but the running service has not loaded it yet. */
  loaded: boolean;
  createdAt: ISODate | null;
  updatedAt: ISODate | null;
}

export interface TrustedSiteInput {
  url: string;
  name: string;
  topics: string[];
  description: string;
}

export type TrustedSitePatch = Partial<Pick<TrustedSite, 'name' | 'topics' | 'description' | 'enabled'>>;

export interface SourcePatch {
  status?: SourceStatus;
  statusNote?: string;
  tier?: Source['tier'];
}

// ── Models and providers (swappable) ────────────────────────────────────────

export type PipelineRole =
  | 'claim_extraction'
  | 'answer_generation'
  | 'embedding'
  | 'ocr'
  | 'transcription'
  | 'reverse_image';

export type ProviderProtocol =
  | 'openai_compatible'
  | 'anthropic'
  | 'google'
  | 'ollama'
  | 'http_custom';

export type ProcessingRegion = 'PL' | 'EOG' | 'poza_EOG' | 'self_hosted';

export type Health = 'ok' | 'degraded' | 'down' | 'unknown';

export interface ModelProvider {
  id: string;
  name: string;
  vendor: string;
  protocol: ProviderProtocol;
  model: string;
  baseUrl: string;
  region: ProcessingRegion;
  roles: PipelineRole[];
  /**
   * Name of the server-side secret holding the API key. The key itself never
   * reaches the browser; the API only reports whether it is configured.
   */
  keyRef?: string;
  keyConfigured: boolean;
  costPer1kInputPln: number;
  costPer1kOutputPln: number;
  health: Health;
  latencyP50Ms?: number;
  errorRate?: number;
  lastCheckedAt?: ISODate;
  notes?: string;
}

export type ProviderInput = Omit<
  ModelProvider,
  'id' | 'keyConfigured' | 'health' | 'latencyP50Ms' | 'errorRate' | 'lastCheckedAt'
>;

export interface PipelineAssignment {
  role: PipelineRole;
  providerId: string | null;
  fallbackProviderIds: string[];
  enabled: boolean;
  params: {
    temperature?: number;
    timeoutS: number;
    maxRetries: number;
  };
  updatedAt: ISODate;
  updatedBy: string;
}

export interface AssignmentPatch {
  providerId?: string | null;
  fallbackProviderIds?: string[];
  enabled?: boolean;
  params?: Partial<PipelineAssignment['params']>;
}

export interface ProviderTestResult {
  ok: boolean;
  latencyMs: number;
  message: string;
}

// ── Channels ────────────────────────────────────────────────────────────────

export interface ChannelInfo {
  id: string;
  name: string;
  kind: 'web' | 'whatsapp' | 'sms' | 'messenger' | 'discord' | 'other';
  enabled: boolean;
  demoAdapter: boolean;
  health: Health;
  requests24h: number;
  medianLatencyMs: number;
  consistency: { passed: number; total: number; lastRunAt?: ISODate };
  operatorCostNote?: string;
}

// ── Security ────────────────────────────────────────────────────────────────

export type SecurityEventType =
  | 'prompt_injection'
  | 'rate_limited'
  | 'ssrf_blocked'
  | 'invalid_input'
  | 'auth_failed';

export interface SecurityEvent {
  id: string;
  at: ISODate;
  type: SecurityEventType;
  channel: string;
  detail: string;
  action: 'instructions_ignored' | 'blocked' | 'throttled' | 'logged';
  checkId?: string;
}

// ── Settings ────────────────────────────────────────────────────────────────

export interface RiskTopic {
  id: string;
  label: string;
  keywords: string[];
  severity: Severity;
}

export interface AlertRules {
  informationGap: {
    enabled: boolean;
    minQueries: number;
    windowHours: number;
    /** Share of queries in the group that ended without evidence (0–1). */
    minNoEvidenceRatio: number;
    similarityThreshold: number;
  };
  querySurge: {
    enabled: boolean;
    minQueries: number;
    windowHours: number;
    /** Current window must be at least this many times the previous one. */
    growthFactor: number;
  };
  highRisk: {
    enabled: boolean;
    /** Notify recipients at once, even for a single query. */
    notifyImmediately: boolean;
    topics: RiskTopic[];
  };
  promptInjection: {
    enabled: boolean;
    minEventsPerHour: number;
  };
  /** User ids notified per alert type. Empty → only a recommendation is shown. */
  recipients: Partial<Record<AlertType, string[]>>;
  notifyByEmail: boolean;
}

export interface PrivacySettings {
  retentionDays: number;
  maskPii: boolean;
  storeFullContent: boolean;
  anonymizeAfterDays: number;
  logIpAddresses: boolean;
}

// ── Dashboard ───────────────────────────────────────────────────────────────

export interface QualityMetric {
  key: string;
  label: string;
  value: number;
  target: number;
  unit: '%' | 's' | '';
  /** `min` = value must be ≥ target, `max` = value must be ≤ target. */
  direction: 'min' | 'max';
}

export interface DashboardStats {
  rangeHours: number;
  generatedAt: ISODate;
  checks: number;
  abstained: number;
  technicalErrors: number;
  injectionsBlocked: number;
  medianLatencyMs: number;
  p95LatencyMs: number;
  costTotalPln: number;
  costPer1000Pln: number;
  verdicts: Partial<Record<Verdict, number>>;
  channels: Record<string, number>;
  /** One bucket per hour (≤ 48 h ranges) or per day. */
  series: { t: ISODate; total: number; abstained: number }[];
  openCases: number;
  activeAlerts: number;
  criticalAlerts: number;
  informationGaps: number;
  quality: QualityMetric[];
  qualityEvaluatedAt?: ISODate;
  /** Only from backend/admin: distinct end users, refused and dangerous queries, blocks. */
  users?: number;
  refused?: number;
  dangerousQueries?: number;
  blockedUsers?: number;
  /** Queries still in progress. */
  pending?: number;
}

// ── Audit ───────────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: string;
  at: ISODate;
  actor: string;
  action: string;
  target: string;
  detail?: string;
}

// ── Only in the real backend (backend/admin) ───────────────────────────────

/**
 * Optional parts of the panel. Each data source declares what it supports;
 * navigation, routes and page sections are hidden for missing features.
 */
export type Feature =
  // example contract (admin_panel/openapi.yaml), implemented by the mock
  | 'cases'
  | 'clusters'
  | 'sources'
  | 'providers'
  | 'channels'
  | 'privacy'
  | 'securityEvents'
  | 'alertRules'
  | 'staffUsers'
  | 'deleteCheck'
  | 'checkCost'
  | 'channelFilter'
  | 'quality'
  // backend/admin
  /** Accounts with passwords stored (hashed) by the source: set and change passwords. */
  | 'passwords'
  | 'endUsers'
  | 'gapLifecycle'
  | 'runtimeConfig'
  | 'techEvents'
  | 'retention'
  /** Trusted sites searched by the verification (`trusted_sources` table + live registry). */
  | 'trustedSites'
  /** Threat report built from the observability logs (`GET /threats`). */
  | 'threats';

export interface ApiCapabilities {
  features: ReadonlySet<Feature>;
  /** Alert types this source can produce (filters list only these). */
  alertTypes: readonly AlertType[];
  /** Check flags this source can filter by. */
  checkFlags: readonly CheckFlag[];
  /** Non-verdict outcomes this source can filter by. */
  checkOutcomes: readonly CheckOutcome[];
}

/** Information-gap lifecycle in backend/admin (`podejrzenie` → … → `zamknieta`). */
export type GapStatus = 'suspected' | 'active' | 'in_progress' | 'closed' | 'rejected';

/** A person who writes to the service (e.g. the WhatsApp bot), known only by a pseudonym. */
export interface EndUser {
  key: string;
  /** Masked identifier, e.g. `***456`. */
  label: string;
  firstSeen: ISODate;
  lastSeen: ISODate;
  queries: number;
  /** Queries classified as dangerous content (medium or high risk). */
  dangerous: number;
  blockedUntil: ISODate | null;
  blockReason: string | null;
  blocked: boolean;
  /** Blocked with no end date. */
  permanent: boolean;
}

export interface EndUserDetail extends EndUser {
  totalQueries: number;
  recentQueries: CheckRecord[];
  alerts: Alert[];
}

export type EndUserFilter = 'all' | 'flagged' | 'blocked';

/** Overrides kept in `runtime_config.json`; `null` = value from `.env`. Keys mirror backend/admin/runtime.py. */
export interface LlmSettings {
  model: string | null;
  text_analysis_model: string | null;
  base_url: string | null;
  timeout_s: number | null;
  max_retries: number | null;
}

export interface ApiSettings {
  disabled_clients: string[] | null;
  article_scraping_enabled: boolean | null;
  article_extractor: 'local' | 'diffbot' | null;
}

export interface MonitoringSettings {
  info_gap_min_users: number;
  info_gap_window_hours: number;
  disinfo_min_users: number;
  disinfo_window_hours: number;
  dangerous_alert_after: number;
  dangerous_block_after: number;
  dangerous_window_hours: number;
  dangerous_block_hours: number;
  auto_block: boolean;
  refuse_high_risk: boolean;
  retention_days: number;
}

export type SecretName = 'freellm_api_key' | 'google_fact_check_api_key' | 'diffbot_api_token';

export interface SecretState {
  /** Set in the panel (runtime_config.json), not only in `.env`. */
  overridden: boolean;
  /** The backend has a value (from either source). */
  set: boolean;
  /** Last characters only, e.g. `****abcd`. The key itself never reaches the browser. */
  mask: string | null;
}

export interface RuntimeConfig {
  llm: LlmSettings;
  apis: ApiSettings;
  monitoring: MonitoringSettings;
  secrets: Record<SecretName, SecretState>;
  /** Environment variable → value the backend uses now (secrets masked). */
  effective: Record<string, string | null>;
  /** apiReading clients that can be switched off. */
  apiClients: string[];
  /** Where the backend stores the overrides. */
  file: string;
}

export interface RuntimeConfigPatch {
  llm?: Partial<LlmSettings>;
  apis?: Partial<ApiSettings>;
  monitoring?: Partial<MonitoringSettings>;
  /** Write-only; `null` removes the override (back to `.env`). */
  secrets?: Partial<Record<SecretName, string | null>>;
}

export interface ConfigChange {
  field: string;
  old: unknown;
  new: unknown;
}

export interface AvailableModels {
  baseUrl: string | null;
  current?: string | null;
  models: string[];
  error?: string;
}

/** One line of the observability log (`backend/logs/app.jsonl`). */
export interface TechEvent {
  id: string;
  at: ISODate;
  level: string;
  event: string;
  requestId?: string;
  /** Every other field of the log line. */
  fields: Record<string, unknown>;
}

export interface TechEventQuery {
  event?: string;
  level?: string;
  requestId?: string;
  sinceHours?: number;
  limit?: number;
}

/** `observability.report.summarize()` as returned by `GET /events/summary`. */
export interface TechSummary {
  requests: {
    count: number;
    failed: number;
    abstained: number;
    duration_ms_p50: number | null;
    duration_ms_p95: number | null;
    cost_usd_total: number;
    cost_usd_avg: number | null;
    cost_incomplete: number;
  };
  llm: {
    latency_ms_p50: number | null;
    latency_ms_p95: number | null;
    by_model: Record<
      string,
      { calls: number; errors: number; prompt_tokens: number; completion_tokens: number; cost_usd: number }
    >;
  };
  search: {
    calls: number;
    errors: Record<string, number>;
    latency_ms_p95: number | null;
    empty_evidence: Record<string, number>;
  };
  prompt_injection: { by_kind: Record<string, number>; by_source: Record<string, number> };
  abstain: Record<string, number>;
  stages_ms_p50: Record<string, number | null>;
  error_lines: number;
}

export interface PurgeResult {
  before: ISODate;
  deleted: { queries: number; claims: number };
}

// ── Threats (backend/admin/threats.py, built from the log file) ──────────────

/** Who and what an event refers to, filled in from the query journal when possible. */
export interface ThreatSubject {
  userKey: string | null;
  userLabel: string | null;
  channel: string | null;
  queryId: string | null;
  /** Text of the query (people with access to the verification history see it anyway). */
  text: string | null;
}

export interface InjectionEvent extends ThreatSubject {
  at: ISODate;
  requestId: string | null;
  /** `input` (the person's message), `text` / `url` (analysed text) or a fetched source. */
  source: string | null;
  kind: string | null;
  detector: string | null;
  pattern: string | null;
  snippet: string | null;
  /** The same text seen this many times in the period (possible coordinated attempt). */
  repeats: number;
}

export interface ManipulationCampaign {
  alertId: string | null;
  title: string;
  claim: string | null;
  topicId: string | null;
  status: string | null;
  severity: string | null;
  users: number;
  count: number | null;
  /** Log events raised for this campaign in the period. */
  signals: number;
  firstSignal: ISODate;
  lastSignal: ISODate;
}

export interface CriticalQueryEvent extends ThreatSubject {
  at: ISODate;
  refused: boolean;
  reason: string | null;
  severity: string | null;
  categories: string[];
  requestId: string | null;
}

export interface BlockedUserEvent {
  at: ISODate;
  userKey: string | null;
  userLabel: string | null;
  until: string | null;
  stillBlocked: boolean;
}

export interface ThreatReport {
  file: string;
  logAvailable: boolean;
  since: ISODate;
  until: ISODate;
  hours: number;
  eventsScanned: number;
  summary: {
    promptInjection: number;
    promptInjectionUsers: number;
    manipulationCampaigns: number;
    criticalQueries: number;
    criticalUsers: number;
    refused: number;
    blockedUsers: number;
  };
  timeline: { bucket: ISODate; promptInjection: number; manipulation: number; critical: number }[];
  injection: {
    bySource: Record<string, number>;
    byDetector: Record<string, number>;
    repeatedTexts: number;
    recent: InjectionEvent[];
  };
  campaigns: ManipulationCampaign[];
  critical: {
    byCategory: Record<string, number>;
    bySeverity: Record<string, number>;
    recent: CriticalQueryEvent[];
    blocked: BlockedUserEvent[];
  };
}
