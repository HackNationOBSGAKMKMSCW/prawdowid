import type {
  Alert,
  AlertQuery,
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

  setToken(token: string | null): void;
  /** Called when the backend rejects the session (HTTP 401). */
  onUnauthorized(handler: () => void): void;

  login(email: string, password: string): Promise<Session>;
  logout(): Promise<void>;
  me(): Promise<User>;
  health(): Promise<{ status: string; version?: string }>;

  getDashboard(rangeHours: number): Promise<DashboardStats>;

  listAlerts(query?: AlertQuery): Promise<Alert[]>;
  updateAlert(id: string, patch: { status: AlertStatus }): Promise<Alert>;
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
  createUser(input: { email: string; name: string; role: Role }): Promise<User>;
  updateUser(id: string, patch: { role?: Role; active?: boolean }): Promise<User>;

  listAudit(): Promise<AuditEntry[]>;
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
