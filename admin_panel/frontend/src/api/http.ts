import type { AdminConfig } from '../config.ts';
import { type AdminApi, ApiError } from './AdminApi.ts';
import { buildPath, type EndpointKey } from './endpoints.ts';
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

type Query = Record<string, string | number | boolean | undefined | null>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  params?: Record<string, string>;
  query?: Query;
  body?: unknown;
}

const STATUS_MESSAGES: Record<number, string> = {
  400: 'Nieprawidłowe dane w żądaniu.',
  401: 'Sesja wygasła lub dane logowania są nieprawidłowe.',
  403: 'Brak uprawnień do tej operacji.',
  404: 'Nie znaleziono zasobu.',
  409: 'Konflikt — dane zmieniły się w międzyczasie. Odśwież widok.',
  422: 'Dane nie przeszły walidacji.',
  429: 'Zbyt wiele żądań. Spróbuj ponownie za chwilę.',
  500: 'Błąd serwera.',
  502: 'Serwer API jest niedostępny (502).',
  503: 'Usługa chwilowo niedostępna (503).',
};

/** Talks to the real admin API described in `admin_panel/openapi.yaml`. */
export class HttpAdminApi implements AdminApi {
  readonly mode = 'http' as const;
  readonly target: string;
  private token: string | null = null;
  private unauthorizedHandler: (() => void) | null = null;
  private readonly config: AdminConfig;

  constructor(config: AdminConfig) {
    this.config = config;
    this.target = config.apiBaseUrl;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  onUnauthorized(handler: () => void): void {
    this.unauthorizedHandler = handler;
  }

  private url(key: EndpointKey, params?: Record<string, string>, query?: Query): string {
    const base = this.config.apiBaseUrl.replace(/\/+$/, '');
    const path = buildPath(this.config.endpoints, key, params);
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(query ?? {})) {
      if (v !== undefined && v !== null && v !== '' && v !== 'any') search.set(k, String(v));
    }
    const qs = search.toString();
    return `${base}${path}${qs ? `?${qs}` : ''}`;
  }

  private async request<T>(key: EndpointKey, options: RequestOptions = {}): Promise<T> {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), this.config.requestTimeoutMs);
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    let res: Response;
    try {
      res = await fetch(this.url(key, options.params, options.query), {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
        credentials: 'same-origin',
      });
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        throw new ApiError('Przekroczono czas oczekiwania na odpowiedź API.');
      }
      throw new ApiError('Brak połączenia z API panelu. Sprawdź adres w konfiguracji.');
    } finally {
      window.clearTimeout(timer);
    }

    if (res.status === 401 && key !== 'login') this.unauthorizedHandler?.();
    if (!res.ok) {
      let detail = '';
      try {
        const body = (await res.json()) as { detail?: unknown; message?: unknown };
        const raw = body.detail ?? body.message;
        if (typeof raw === 'string') detail = raw;
      } catch {
        // Body was not JSON; fall back to the generic message.
      }
      throw new ApiError(detail || STATUS_MESSAGES[res.status] || `Błąd API (${res.status}).`, res.status);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  login(email: string, password: string): Promise<Session> {
    return this.request('login', { method: 'POST', body: { email, password } });
  }
  async logout(): Promise<void> {
    try {
      await this.request('logout', { method: 'POST' });
    } catch {
      // Logging out locally must work even if the API is down.
    }
  }
  me(): Promise<User> {
    return this.request('me');
  }
  health(): Promise<{ status: string; version?: string }> {
    return this.request('health');
  }

  getDashboard(rangeHours: number): Promise<DashboardStats> {
    return this.request('dashboard', { query: { rangeHours } });
  }

  listAlerts(query: AlertQuery = {}): Promise<Alert[]> {
    return this.request('alerts', { query: { ...query } });
  }
  updateAlert(id: string, patch: { status: AlertStatus }): Promise<Alert> {
    return this.request('alert', { method: 'PATCH', params: { id }, body: patch });
  }
  escalateAlert(id: string, assigneeId?: string): Promise<ModeratorCase> {
    return this.request('alertEscalate', { method: 'POST', params: { id }, body: { assigneeId } });
  }

  listClusters(query: ClusterQuery = {}): Promise<QueryCluster[]> {
    return this.request('clusters', { query: { ...query } });
  }
  getCluster(id: string): Promise<QueryCluster> {
    return this.request('cluster', { params: { id } });
  }

  listCases(query: CaseQuery = {}): Promise<ModeratorCase[]> {
    return this.request('cases', { query: { ...query } });
  }
  getCase(id: string): Promise<ModeratorCase> {
    return this.request('case', { params: { id } });
  }
  updateCase(id: string, patch: CasePatch): Promise<ModeratorCase> {
    return this.request('case', { method: 'PATCH', params: { id }, body: patch });
  }
  addCaseComment(id: string, text: string): Promise<ModeratorCase> {
    return this.request('caseComments', { method: 'POST', params: { id }, body: { text } });
  }
  forwardCase(id: string, userId: string, note?: string): Promise<ModeratorCase> {
    return this.request('caseForward', { method: 'POST', params: { id }, body: { userId, note } });
  }

  listChecks(query: CheckQuery = {}): Promise<Page<CheckRecord>> {
    return this.request('checks', { query: { ...query } });
  }
  getCheck(id: string): Promise<CheckRecord> {
    return this.request('check', { params: { id } });
  }
  deleteCheck(id: string): Promise<void> {
    return this.request('check', { method: 'DELETE', params: { id } });
  }

  listSources(): Promise<Source[]> {
    return this.request('sources');
  }
  createSource(input: SourceInput): Promise<Source> {
    return this.request('sources', { method: 'POST', body: input });
  }
  updateSource(id: string, patch: SourcePatch): Promise<Source> {
    return this.request('source', { method: 'PATCH', params: { id }, body: patch });
  }
  refreshSource(id: string): Promise<Source> {
    return this.request('sourceRefresh', { method: 'POST', params: { id } });
  }

  listProviders(): Promise<ModelProvider[]> {
    return this.request('providers');
  }
  createProvider(input: ProviderInput): Promise<ModelProvider> {
    return this.request('providers', { method: 'POST', body: input });
  }
  deleteProvider(id: string): Promise<void> {
    return this.request('provider', { method: 'DELETE', params: { id } });
  }
  testProvider(id: string): Promise<ProviderTestResult> {
    return this.request('providerTest', { method: 'POST', params: { id } });
  }
  listAssignments(): Promise<PipelineAssignment[]> {
    return this.request('assignments');
  }
  updateAssignment(role: PipelineRole, patch: AssignmentPatch): Promise<PipelineAssignment> {
    return this.request('assignment', { method: 'PATCH', params: { role }, body: patch });
  }

  listChannels(): Promise<ChannelInfo[]> {
    return this.request('channels');
  }
  updateChannel(id: string, patch: { enabled: boolean }): Promise<ChannelInfo> {
    return this.request('channel', { method: 'PATCH', params: { id }, body: patch });
  }

  listSecurityEvents(sinceHours?: number): Promise<SecurityEvent[]> {
    return this.request('securityEvents', { query: { sinceHours } });
  }

  getAlertRules(): Promise<AlertRules> {
    return this.request('alertRules');
  }
  updateAlertRules(rules: AlertRules): Promise<AlertRules> {
    return this.request('alertRules', { method: 'PUT', body: rules });
  }
  getPrivacy(): Promise<PrivacySettings> {
    return this.request('privacy');
  }
  updatePrivacy(settings: PrivacySettings): Promise<PrivacySettings> {
    return this.request('privacy', { method: 'PUT', body: settings });
  }
  purgeDemoData(): Promise<{ deletedChecks: number }> {
    return this.request('purgeDemo', { method: 'POST' });
  }

  listUsers(): Promise<User[]> {
    return this.request('users');
  }
  createUser(input: { email: string; name: string; role: Role }): Promise<User> {
    return this.request('users', { method: 'POST', body: input });
  }
  updateUser(id: string, patch: { role?: Role; active?: boolean }): Promise<User> {
    return this.request('user', { method: 'PATCH', params: { id }, body: patch });
  }

  listAudit(): Promise<AuditEntry[]> {
    return this.request('audit');
  }
}
