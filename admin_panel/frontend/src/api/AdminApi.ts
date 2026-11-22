import type {
  Alert,
  AlertQuery,
  ApiCapabilities,
  AvailableModels,
  ConfigChange,
  GapStatus,
  PurgeResult,
  RuntimeConfig,
  RuntimeConfigPatch,
  TechEvent,
  TechEventQuery,
  TechSummary,
  ThreatReport,
  TrustedSite,
  TrustedSiteInput,
  TrustedSitePatch,
  AlertRules,
  AlertStatus,
  AssignmentPatch,
  AuditEntry,
  CasePatch,
  CaseQuery,
  ChannelInfo,
  CheckQuery,
  CheckRecord,
  ClusterQuery,
  DashboardStats,
  ModelProvider,
  ModeratorCase,
  Page,
  PipelineAssignment,
  PipelineRole,
  PrivacySettings,
  ProviderInput,
  ProviderTestResult,
  QueryCluster,
  Role,
  SecurityEvent,
  Session,
  Source,
  SourceInput,
  SourcePatch,
  User,
} from './types.ts';

/**
 * Everything the panel needs from a backend. Pages talk only to this
 * interface; `api/index.ts` picks the implementation from the config, so a
 * new backend (or a different transport) is one new class, not a rewrite.
 */
export interface AdminApi {
  readonly mode: 'mock' | 'http';
  /** Where requests go — shown in the UI so operators know what they are looking at. */
  readonly target: string;
  /** What this source supports; the panel hides views and actions it cannot serve. */
  readonly capabilities: ApiCapabilities;

  /** `user`: who signed in, so the source can skip calls the role is not allowed to make. */
  setToken(token: string | null, user?: User | null): void;
  /** Called when the backend rejects the session (HTTP 401). */
  onUnauthorized(handler: () => void): void;

  login(email: string, password: string): Promise<Session>;
  logout(): Promise<void>;
  me(): Promise<User>;
  health(): Promise<{ status: string; version?: string }>;

  getDashboard(rangeHours: number): Promise<DashboardStats>;

  listAlerts(query?: AlertQuery): Promise<Alert[]>;
  updateAlert(id: string, patch: { status: AlertStatus; note?: string }): Promise<Alert>;
  /** Opens a moderator case, or attaches the alert to the existing case of the same group. */
  escalateAlert(id: string, assigneeId?: string): Promise<ModeratorCase>;

  listClusters(query?: ClusterQuery): Promise<QueryCluster[]>;
  getCluster(id: string): Promise<QueryCluster>;

  listCases(query?: CaseQuery): Promise<ModeratorCase[]>;
  getCase(id: string): Promise<ModeratorCase>;
  updateCase(id: string, patch: CasePatch): Promise<ModeratorCase>;
  addCaseComment(id: string, text: string): Promise<ModeratorCase>;
  /** Actually hands the case to a person (as opposed to the system's recommendation). */
  forwardCase(id: string, userId: string, note?: string): Promise<ModeratorCase>;

  listChecks(query?: CheckQuery): Promise<Page<CheckRecord>>;
  getCheck(id: string): Promise<CheckRecord>;
  /** Deletes the stored record of a check (privacy request / demo session). */
  deleteCheck(id: string): Promise<void>;

  listSources(): Promise<Source[]>;
  createSource(input: SourceInput): Promise<Source>;
  updateSource(id: string, patch: SourcePatch): Promise<Source>;
  refreshSource(id: string): Promise<Source>;

  listProviders(): Promise<ModelProvider[]>;
  createProvider(input: ProviderInput): Promise<ModelProvider>;
  deleteProvider(id: string): Promise<void>;
  testProvider(id: string): Promise<ProviderTestResult>;
  listAssignments(): Promise<PipelineAssignment[]>;
  updateAssignment(role: PipelineRole, patch: AssignmentPatch): Promise<PipelineAssignment>;

  listChannels(): Promise<ChannelInfo[]>;
  updateChannel(id: string, patch: { enabled: boolean }): Promise<ChannelInfo>;

  listSecurityEvents(sinceHours?: number): Promise<SecurityEvent[]>;

  getAlertRules(): Promise<AlertRules>;
  updateAlertRules(rules: AlertRules): Promise<AlertRules>;
  getPrivacy(): Promise<PrivacySettings>;
  updatePrivacy(settings: PrivacySettings): Promise<PrivacySettings>;
  purgeDemoData(): Promise<{ deletedChecks: number }>;

  listUsers(): Promise<User[]>;
  /** `password`: initial password, when the source stores accounts itself (`passwords`). */
  createUser(input: { email: string; name: string; role: Role; password?: string }): Promise<User>;
  updateUser(id: string, patch: { role?: Role; active?: boolean }): Promise<User>;

  listAudit(): Promise<AuditEntry[]>;

  /** `passwords`: the signed-in person changes their own password (ends their sessions). */
  changeOwnPassword(currentPassword: string, newPassword: string): Promise<void>;
  /** `passwords`: an administrator sets a new password for an account. */
  resetUserPassword(id: string, password: string): Promise<void>;

  // ── Features of the real backend (backend/admin) ──────────────────────────
  // Gated by `capabilities.features`; sources without them reject the call.

  /** `gapLifecycle`: move an information gap through its states. */
  updateGapStatus(clusterId: string, status: GapStatus, note?: string): Promise<QueryCluster>;

  /** `runtimeConfig`: models, data APIs, keys and alert thresholds, changed without a restart. */
  getRuntimeConfig(): Promise<RuntimeConfig>;
  updateRuntimeConfig(patch: RuntimeConfigPatch): Promise<{ changes: ConfigChange[]; config: RuntimeConfig }>;
  listAvailableModels(): Promise<AvailableModels>;

  /** `techEvents`: observability log lines and their summary. */
  listTechEvents(query?: TechEventQuery): Promise<{ file: string; items: TechEvent[] }>;
  getTechSummary(sinceHours?: number): Promise<TechSummary>;

  /** `trustedSites`: the sites the verification searches (keyed by URL). */
  listTrustedSites(): Promise<TrustedSite[]>;
  createTrustedSite(input: TrustedSiteInput): Promise<TrustedSite>;
  updateTrustedSite(url: string, patch: TrustedSitePatch): Promise<TrustedSite>;
  deleteTrustedSite(url: string): Promise<void>;
  /** Fetches the site again and re-detects how to search it. */
  checkTrustedSite(url: string): Promise<TrustedSite>;

  /** `threats`: prompt injection, manipulation campaigns and critical queries from the logs. */
  getThreats(hours: number): Promise<ThreatReport>;

  /** `retention`: delete stored queries older than N days (default: retention setting). */
  purgeOldData(olderThanDays?: number): Promise<PurgeResult>;
}

/** Error for a feature the data source does not have. */
export function unsupported(what: string): ApiError {
  return new ApiError(`${what}: niedostępne w tym źródle danych.`, 501);
}

/** Error with a user-facing Polish message and the HTTP status, if any. */
export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
