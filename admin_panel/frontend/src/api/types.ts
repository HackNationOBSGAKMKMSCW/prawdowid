/**
 * Domain types shared by every data source (mock and HTTP). They mirror the
 * schemas in `admin_panel/openapi.yaml`; change both together.
 */

export type ISODate = string;

// ── Users and sessions ──────────────────────────────────────────────────────

export type Role = 'admin' | 'moderator' | 'analyst';

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
export type CheckOutcome = 'verdict' | 'abstained' | 'technical_error' | 'needs_clarification';

export type EvidenceStrength = 'strong' | 'moderate' | 'weak' | 'none';

export type InputKind = 'text' | 'url' | 'image';

export type CheckFlag =
  | 'prompt_injection'
  | 'high_risk'
  | 'pii_masked'
  | 'archival_material'
  | 'incident_match'
  | 'source_status_warning'
  | 'conflicting_sources';

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
  verdict: Verdict;
  strength: EvidenceStrength;
  rationale: string;
  evidence: Evidence[];
  /** What could not be established — filled in when the system abstains. */
  missing?: string;
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
}

export interface ClusterQuery {
  onlyGaps?: boolean;
  onlySurging?: boolean;
  search?: string;
}

// ── Alerts and warnings ─────────────────────────────────────────────────────

export type AlertType =
  | 'information_gap'
  | 'query_surge'
  | 'high_risk'
  | 'prompt_injection'
  | 'incident_match'
  | 'source_status'
  | 'system';

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
