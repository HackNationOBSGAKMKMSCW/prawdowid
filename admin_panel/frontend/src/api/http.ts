import { can } from '../auth/permissions.ts';
import type { AdminConfig } from '../config.ts';
import { type AdminApi, ApiError, unsupported } from './AdminApi.ts';
import {
  ALERT_STATUS_TO_BACKEND,
  ALERT_TYPE_TO_BACKEND,
  BACKEND_ALERT_TYPES,
  BACKEND_FLAGS,
  FLAG_TO_BACKEND,
  GAP_TO_BACKEND,
  joinTrustedSites,
  mapAccount,
  mapThreats,
  mapActivity,
  mapAlert,
  mapAudit,
  mapConfig,
  mapEvent,
  mapQuery,
  mapTopic,
  mapVerdict,
  outcomeFilter,
  outcomeOf,
  VERDICT_TO_BACKEND,
} from './backend/mappers.ts';
import type {
  RawAccount,
  RawActivity,
  RawAlert,
  RawAudit,
  RawConfig,
  RawDashboard,
  RawEvent,
  RawGap,
  RawQuery,
  RawQueryPage,
  RawSourceStatus,
  RawTopic,
  RawTrustedSource,
} from './backend/raw.ts';
import { buildPath, type EndpointKey } from './endpoints.ts';
import type {
  Alert,
  AlertQuery,
  AlertRules,
  AlertStatus,
  ApiCapabilities,
  AuditEntry,
  AvailableModels,
  ChannelInfo,
  CheckQuery,
  CheckRecord,
  ClusterQuery,
  ConfigChange,
  DashboardStats,
  GapStatus,
  ModelProvider,
  ModeratorCase,
  MonitoringSettings,
  Page,
  PipelineAssignment,
  PrivacySettings,
  ProviderTestResult,
  PurgeResult,
  QueryCluster,
  Role,
  RuntimeConfig,
  RuntimeConfigPatch,
  SecurityEvent,
  Session,
  Source,
  TechEvent,
  TechEventQuery,
  TechSummary,
  ThreatReport,
  TrustedSite,
  TrustedSiteInput,
  TrustedSitePatch,
  User,
  Verdict,
} from './types.ts';

type QueryValue = string | number | boolean | undefined | null;
type Query = Record<string, QueryValue | QueryValue[]>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  params?: Record<string, string>;
  query?: Query;
  body?: unknown;
  /** Do not sign out on 401 (a failed login is not an expired session). */
  quiet401?: boolean;
}

const STATUS_MESSAGES: Record<number, string> = {
  400: 'Nieprawidłowe dane w żądaniu.',
  401: 'Sesja wygasła lub token administratora jest nieprawidłowy.',
  403: 'Brak uprawnień do tej operacji.',
  404: 'Nie znaleziono zasobu.',
  409: 'Konflikt — dane zmieniły się w międzyczasie. Odśwież widok.',
  422: 'Dane nie przeszły walidacji.',
  429: 'Zbyt wiele żądań. Spróbuj ponownie za chwilę.',
  500: 'Błąd serwera.',
  502: 'Serwer API jest niedostępny (502).',
  503: 'Usługa chwilowo niedostępna (503).',
};

const HOUR = 3_600_000;
const PAGE_LIMIT = 500;
/** Most queries read to build the dashboard series; above it the series is a sample. */
const DASHBOARD_QUERY_CAP = 5000;
/** Topics whose details are loaded for the information-gap list. */
const TOPIC_DETAIL_CAP = 60;
const ALL_GAP_STATUSES = ['podejrzenie', 'aktywna', 'w_uzupelnianiu', 'zamknieta', 'odrzucona'];
const OPEN_GAP_STATUSES = ['podejrzenie', 'aktywna', 'w_uzupelnianiu'];

const iso = (ms: number) => new Date(ms).toISOString();

function errorDetail(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const raw = (body as { detail?: unknown; message?: unknown }).detail ?? (body as { message?: unknown }).message;
  if (typeof raw === 'string') return raw;
  // FastAPI validation errors: [{ loc: [...], msg: "..." }, ...]
  if (Array.isArray(raw)) {
    return raw
      .map((e) => (e && typeof e === 'object' && 'msg' in e ? String((e as { msg: unknown }).msg) : ''))
      .filter(Boolean)
      .join('; ');
  }
  return '';
}

/**
 * Talks to the real admin API, `backend/admin` (FastAPI, `/api/admin`), and
 * maps its responses onto the panel's domain types (`backend/mappers.ts`).
 *
 * The backend authenticates with one shared token (`ADMIN_API_TOKEN`), so the
 * panel signs in with that token and a name that goes to the audit log.
 * Parts of the example contract it does not implement (cases, source
 * catalogue, provider registry, …) are switched off in `capabilities`.
 */
export class HttpAdminApi implements AdminApi {
  readonly mode = 'http' as const;
  readonly target: string;
  readonly capabilities: ApiCapabilities = {
    features: new Set([
      'staffUsers',
      'passwords',
      'gapLifecycle',
      'runtimeConfig',
      'techEvents',
      'retention',
      'trustedSites',
      'threats',
    ]),
    alertTypes: BACKEND_ALERT_TYPES,
    checkFlags: BACKEND_FLAGS,
    checkOutcomes: ['abstained', 'technical_error', 'refused', 'pending'],
  };
  private token: string | null = null;
  private unauthorizedHandler: (() => void) | null = null;
  private readonly config: AdminConfig;
  private monitoring: { at: number; value: MonitoringSettings | null } | null = null;
  /** The role may not read the config (403): stop asking until the next sign-in. */
  private monitoringForbidden = false;

  constructor(config: AdminConfig) {
    this.config = config;
    this.target = config.apiBaseUrl;
  }

  setToken(token: string | null, user?: User | null): void {
    this.token = token;
    this.monitoring = null;
    // Alert rule texts need the thresholds from /config, which only some roles may read.
    this.monitoringForbidden = !!user && !can(user, 'settings:read');
  }

  onUnauthorized(handler: () => void): void {
    this.unauthorizedHandler = handler;
  }

  // ── transport ─────────────────────────────────────────────────────────────

  private url(key: EndpointKey, params?: Record<string, string>, query?: Query): string {
    const base = this.config.apiBaseUrl.replace(/\/+$/, '');
    const path = buildPath(this.config.endpoints, key, params);
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(query ?? {})) {
      for (const item of Array.isArray(v) ? v : [v]) {
        if (item !== undefined && item !== null && item !== '' && item !== 'any') search.append(k, String(item));
      }
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
      throw new ApiError(
        `Brak połączenia z API panelu (${this.target}). Sprawdź, czy backend admina działa, i adres w config.json.`,
      );
    } finally {
      window.clearTimeout(timer);
    }

    if (res.status === 401 && !options.quiet401) this.unauthorizedHandler?.();
    if (!res.ok) {
      let detail = '';
      try {
        detail = errorDetail(await res.json());
      } catch {
        // Body was not JSON; fall back to the generic message.
      }
      throw new ApiError(detail || STATUS_MESSAGES[res.status] || `Błąd API (${res.status}).`, res.status);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  /** Thresholds used to describe alert rules; cached for a minute, optional. */
  private async monitoringSettings(): Promise<MonitoringSettings | null> {
    if (this.monitoringForbidden) return null;
    if (this.monitoring && Date.now() - this.monitoring.at < 60_000) return this.monitoring.value;
    let value: MonitoringSettings | null = null;
    try {
      value = (await this.request<RawConfig>('config')).monitoring;
    } catch (err) {
      // Alerts still render, only with a generic rule description.
      if (err instanceof ApiError && err.status === 403) this.monitoringForbidden = true;
    }
    this.monitoring = { at: Date.now(), value };
    return value;
  }

  /** Reads every query since `since`, page by page, up to `cap`. */
  private async queriesSince(since: string, cap: number): Promise<{ items: RawQuery[]; total: number }> {
    const items: RawQuery[] = [];
    let total = 0;
    for (let offset = 0; offset < cap; offset += PAGE_LIMIT) {
      const page = await this.request<RawQueryPage>('queries', {
        query: { since, limit: Math.min(PAGE_LIMIT, cap - offset), offset },
      });
      total = page.total;
      items.push(...page.items);
      if (items.length >= page.total || page.items.length === 0) break;
    }
    return { items, total };
  }

  // ── session ───────────────────────────────────────────────────────────────

  /** Accounts live in the backend; passwords and session tokens are stored there only as hashes. */
  async login(email: string, password: string): Promise<Session> {
    let raw: { token: string; expiresAt: string | null; user: RawAccount };
    try {
      raw = await this.request('login', { method: 'POST', body: { email, password }, quiet401: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        throw new ApiError('Backend działa bez bazy kont: ustaw DATABASE_URL w backend/.env i uruchom go ponownie.', 404);
      }
      throw err;
    }
    // A token without an expiry still ends with the browser tab (sessionStorage).
    const expiresAt = raw.expiresAt ?? new Date(Date.now() + 12 * HOUR).toISOString();
    return { token: raw.token, expiresAt, user: mapAccount(raw.user) };
  }

  async logout(): Promise<void> {
    try {
      await this.request('logout', { method: 'POST', quiet401: true });
    } catch {
      // Signing out locally must work even if the API is down.
    }
  }

  async me(): Promise<User> {
    return mapAccount(await this.request<RawAccount>('me'));
  }

  async changeOwnPassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.request('ownPassword', {
      method: 'POST',
      body: { current: currentPassword, new: newPassword },
    });
  }

  health(): Promise<{ status: string; version?: string }> {
    return this.request('health');
  }

  // ── dashboard ─────────────────────────────────────────────────────────────

  async getDashboard(rangeHours: number): Promise<DashboardStats> {
    const now = Date.now();
    const since = iso(now - rangeHours * HOUR);
    const [stats, list] = await Promise.all([
      this.request<RawDashboard>('dashboard', { query: { hours: rangeHours } }),
      this.queriesSince(since, DASHBOARD_QUERY_CAP),
    ]);

    const verdicts: Partial<Record<Verdict, number>> = {};
    for (const [name, n] of Object.entries(stats.verdicts ?? {})) {
      const v = mapVerdict(name);
      if (v) verdicts[v] = (verdicts[v] ?? 0) + n;
    }

    const step = rangeHours <= 48 ? HOUR : 24 * HOUR;
    const buckets = Math.ceil((rangeHours * HOUR) / step);
    const end = Math.ceil(now / step) * step;
    const start = end - buckets * step;
    const series = Array.from({ length: buckets }, (_, i) => ({ t: iso(start + i * step), total: 0, abstained: 0 }));
    const channels: Record<string, number> = {};
    const durations: number[] = [];
    let abstained = 0;
    for (const q of list.items) {
      const outcome = outcomeOf(q);
      const t = Date.parse(q.ts);
      const index = Math.floor((t - start) / step);
      if (index >= 0 && index < buckets) {
        series[index].total += 1;
        if (outcome === 'abstained') series[index].abstained += 1;
      }
      if (outcome === 'abstained') abstained += 1;
      const channel = q.channel || 'api';
      channels[channel] = (channels[channel] ?? 0) + 1;
      if (q.completed_at && (outcome === 'verdict' || outcome === 'abstained')) {
        const ms = Date.parse(q.completed_at) - t;
        if (ms > 0) durations.push(ms);
      }
    }
    durations.sort((a, b) => a - b);
    const pct = (p: number) => (durations.length ? durations[Math.min(durations.length - 1, Math.floor(p * durations.length))] : 0);
    const statuses = stats.statuses ?? {};

    return {
      rangeHours,
      generatedAt: stats.generated_at,
      checks: stats.queries,
      abstained,
      technicalErrors: (statuses.blad ?? 0) + (stats.verdicts?.blad_analizy ?? 0),
      injectionsBlocked: 0,
      medianLatencyMs: pct(0.5),
      p95LatencyMs: pct(0.95),
      costTotalPln: 0,
      costPer1000Pln: 0,
      verdicts,
      channels,
      series,
      openCases: 0,
      activeAlerts: Object.values(stats.open_alerts ?? {}).reduce((s, n) => s + n, 0),
      criticalAlerts: (stats.latest_alerts ?? []).filter((a) => a.severity === 'krytyczna').length,
      informationGaps: stats.active_info_gaps,
      quality: [],
      refused: statuses.odrzucone ?? 0,
      pending: statuses.w_toku ?? 0,
      dangerousQueries: stats.dangerous_queries,
    };
  }

  // ── alerts ────────────────────────────────────────────────────────────────

  async listAlerts(query: AlertQuery = {}): Promise<Alert[]> {
    const type = query.type && query.type !== 'any' ? ALERT_TYPE_TO_BACKEND[query.type] : undefined;
    if (query.type && query.type !== 'any' && !type) return [];
    const single = query.status && query.status !== 'any' && query.status !== 'open';
    const [rows, monitoring] = await Promise.all([
      this.request<{ items: RawAlert[] }>('alerts', {
        query: { type, status: single ? ALERT_STATUS_TO_BACKEND[query.status as AlertStatus] : undefined, limit: 1000 },
      }),
      this.monitoringSettings(),
    ]);
    return rows.items
      .map((row) => mapAlert(row, monitoring))
      .filter((a) => query.status !== 'open' || a.status === 'new' || a.status === 'acknowledged')
      .filter((a) => !query.severity || query.severity === 'any' || a.severity === query.severity);
  }

  async updateAlert(id: string, patch: { status: AlertStatus; note?: string }): Promise<Alert> {
    const row = await this.request<RawAlert>('alert', {
      method: 'POST',
      params: { id },
      body: { status: ALERT_STATUS_TO_BACKEND[patch.status], note: patch.note ?? null },
    });
    return mapAlert(row, await this.monitoringSettings());
  }

  escalateAlert(): Promise<ModeratorCase> {
    return Promise.reject(unsupported('Sprawy'));
  }

  // ── topics / information gaps ─────────────────────────────────────────────

  async listClusters(query: ClusterQuery = {}): Promise<QueryCluster[]> {
    if (query.onlySurging) return [];
    const { items } = await this.request<{ items: RawGap[] }>('infoGaps', {
      query: { status: query.onlyGaps ? OPEN_GAP_STATUSES : ALL_GAP_STATUSES, limit: 1000 },
    });
    const needle = query.search?.trim().toLowerCase();
    const gaps = needle ? items.filter((g) => g.label.toLowerCase().includes(needle)) : items;
    const now = Date.now();
    return Promise.all(
      gaps.map(async (gap, index) => {
        if (query.light || index >= TOPIC_DETAIL_CAP) return mapTopic(gap, null, now);
        const topic = await this.request<RawTopic>('topic', { params: { id: gap.id } }).catch(() => null);
        return mapTopic(gap, topic, now);
      }),
    );
  }

  async getCluster(id: string): Promise<QueryCluster> {
    const topic = await this.request<RawTopic>('topic', { params: { id } });
    return mapTopic(topic, topic);
  }

  async updateGapStatus(clusterId: string, status: GapStatus, note?: string): Promise<QueryCluster> {
    const topic = await this.request<RawTopic>('infoGap', {
      method: 'POST',
      params: { id: clusterId },
      body: { status: GAP_TO_BACKEND[status], note: note?.trim() || null },
    });
    return mapTopic(topic, topic);
  }

  // ── verification log (user queries) ───────────────────────────────────────

  async listChecks(query: CheckQuery = {}): Promise<Page<CheckRecord>> {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 25;

    if (query.clusterId) {
      // All queries whose claims were grouped into this topic (newest 200 claims).
      const topic = await this.request<RawTopic>('topic', { params: { id: query.clusterId } });
      const ids = [...new Set(topic.claims.map((c) => c.query_id).filter((id): id is string => !!id))];
      const slice = ids.slice((page - 1) * pageSize, page * pageSize);
      const rows = await Promise.all(slice.map((id) => this.request<RawQuery>('query', { params: { id } }).catch(() => null)));
      return { items: rows.filter((r): r is RawQuery => !!r).map(mapQuery), total: ids.length, page, pageSize };
    }

    const filters: Record<string, string | undefined> = {};
    if (query.outcome && query.outcome !== 'any') Object.assign(filters, outcomeFilter(query.outcome));
    if (query.verdict && query.verdict !== 'any') filters.verdict = VERDICT_TO_BACKEND[query.verdict];
    if (query.flag && query.flag !== 'any') {
      const flag = FLAG_TO_BACKEND[query.flag];
      if (!flag) return { items: [], total: 0, page, pageSize };
      filters.flag = flag;
    }
    const search = query.search?.trim();
    const result = await this.request<RawQueryPage>('queries', {
      query: {
        ...filters,
        q: search || undefined,
        since: query.sinceHours ? iso(Date.now() - query.sinceHours * HOUR) : undefined,
        limit: Math.min(pageSize, 500),
        offset: (page - 1) * pageSize,
      },
    });
    return { items: result.items.map(mapQuery), total: result.total, page, pageSize };
  }

  async getCheck(id: string): Promise<CheckRecord> {
    return mapQuery(await this.request<RawQuery>('query', { params: { id } }));
  }

  deleteCheck(): Promise<void> {
    return Promise.reject(unsupported('Usuwanie pojedynczego zapisu'));
  }

  // ── runtime configuration ─────────────────────────────────────────────────

  async getRuntimeConfig(): Promise<RuntimeConfig> {
    const raw = await this.request<RawConfig>('config');
    this.monitoring = { at: Date.now(), value: raw.monitoring };
    return mapConfig(raw);
  }

  async updateRuntimeConfig(patch: RuntimeConfigPatch): Promise<{ changes: ConfigChange[]; config: RuntimeConfig }> {
    const result = await this.request<{ changes: ConfigChange[]; config: RawConfig }>('config', {
      method: 'PATCH',
      body: patch,
    });
    this.monitoring = null;
    // PATCH returns the public view without the client list; read the full config again.
    return { changes: result.changes, config: await this.getRuntimeConfig() };
  }

  async listAvailableModels(): Promise<AvailableModels> {
    const raw = await this.request<{ base_url: string | null; current?: string | null; models: string[]; error?: string }>(
      'configModels',
    );
    return { baseUrl: raw.base_url, current: raw.current, models: raw.models, error: raw.error };
  }

  // ── observability ─────────────────────────────────────────────────────────

  async listTechEvents(query: TechEventQuery = {}): Promise<{ file: string; items: TechEvent[] }> {
    const raw = await this.request<{ file: string; items: RawEvent[] }>('events', {
      query: {
        event: query.event?.trim() || undefined,
        level: query.level,
        request_id: query.requestId?.trim() || undefined,
        since: query.sinceHours ? iso(Date.now() - query.sinceHours * HOUR) : undefined,
        limit: query.limit ?? 200,
      },
    });
    return { file: raw.file, items: raw.items.map(mapEvent).reverse() };
  }

  getTechSummary(sinceHours?: number): Promise<TechSummary> {
    return this.request('eventsSummary', {
      query: { since: sinceHours ? iso(Date.now() - sinceHours * HOUR) : undefined },
    });
  }

  purgeOldData(olderThanDays?: number): Promise<PurgeResult> {
    return this.request('purge', { method: 'POST', body: { older_than_days: olderThanDays ?? null } });
  }

  // ── threats from the logs ─────────────────────────────────────────────────

  async getThreats(hours: number): Promise<ThreatReport> {
    return mapThreats(await this.request<Record<string, unknown>>('threats', { query: { hours } }));
  }

  // ── trusted sites (trusted_sources + the verification's registry) ────────

  async listTrustedSites(): Promise<TrustedSite[]> {
    const [rows, statuses] = await Promise.all([
      this.request<RawTrustedSource[]>('sources'),
      // The panel backend outside the website API has no registry: show the table alone.
      this.request<RawSourceStatus[]>('sourcesStatus').catch(() => [] as RawSourceStatus[]),
    ]);
    return joinTrustedSites(rows, statuses);
  }

  private async trustedSite(url: string): Promise<TrustedSite> {
    const site = (await this.listTrustedSites()).find((s) => s.url === url);
    if (!site) throw new ApiError('Nie znaleziono strony na liście.', 404);
    return site;
  }

  async createTrustedSite(input: TrustedSiteInput): Promise<TrustedSite> {
    const row = await this.request<RawTrustedSource>('sources', { method: 'POST', body: input });
    return this.trustedSite(row.url);
  }

  async updateTrustedSite(url: string, patch: TrustedSitePatch): Promise<TrustedSite> {
    await this.request<RawTrustedSource>('sources', { method: 'PATCH', query: { url }, body: patch });
    return this.trustedSite(url);
  }

  async deleteTrustedSite(url: string): Promise<void> {
    await this.request('sources', { method: 'DELETE', query: { url } });
  }

  async checkTrustedSite(url: string): Promise<TrustedSite> {
    await this.request<RawSourceStatus>('sourcesCheck', { method: 'POST', query: { url } });
    return this.trustedSite(url);
  }

  // ── panel accounts ────────────────────────────────────────────────────────

  async listUsers(): Promise<User[]> {
    const rows = await this.request<RawAccount[] | { items: RawAccount[] }>('accounts');
    return (Array.isArray(rows) ? rows : rows.items).map(mapAccount);
  }

  async createUser(input: { email: string; name: string; role: Role; password?: string }): Promise<User> {
    return mapAccount(await this.request<RawAccount>('accounts', { method: 'POST', body: input }));
  }

  async updateUser(id: string, patch: { role?: Role; active?: boolean }): Promise<User> {
    return mapAccount(await this.request<RawAccount>('account', { method: 'PATCH', params: { id }, body: patch }));
  }

  async resetUserPassword(id: string, password: string): Promise<void> {
    await this.request('accountPassword', { method: 'POST', params: { id }, body: { password } });
  }

  // ── audit ─────────────────────────────────────────────────────────────────

  async listAudit(): Promise<AuditEntry[]> {
    // With PostgreSQL every action (logins, accounts, blocks, config) is in activity_logs;
    // without it only configuration changes are recorded.
    try {
      const { items } = await this.request<{ items: RawActivity[] }>('activity', { query: { limit: 1000 } });
      return items.map(mapActivity);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) throw err;
    }
    const { items } = await this.request<{ items: RawAudit[] }>('configAudit', { query: { limit: 1000 } });
    return items.map(mapAudit);
  }

  // ── parts of the example contract the backend does not have ───────────────
  // Hidden in the UI via `capabilities`; kept so the interface stays one.

  listCases(): Promise<ModeratorCase[]> {
    return Promise.resolve([]);
  }
  getCase(): Promise<ModeratorCase> {
    return Promise.reject(unsupported('Sprawy'));
  }
  updateCase(): Promise<ModeratorCase> {
    return Promise.reject(unsupported('Sprawy'));
  }
  addCaseComment(): Promise<ModeratorCase> {
    return Promise.reject(unsupported('Sprawy'));
  }
  forwardCase(): Promise<ModeratorCase> {
    return Promise.reject(unsupported('Sprawy'));
  }
  listSources(): Promise<Source[]> {
    return Promise.resolve([]);
  }
  createSource(): Promise<Source> {
    return Promise.reject(unsupported('Katalog źródeł'));
  }
  updateSource(): Promise<Source> {
    return Promise.reject(unsupported('Katalog źródeł'));
  }
  refreshSource(): Promise<Source> {
    return Promise.reject(unsupported('Katalog źródeł'));
  }
  listProviders(): Promise<ModelProvider[]> {
    return Promise.resolve([]);
  }
  createProvider(): Promise<ModelProvider> {
    return Promise.reject(unsupported('Rejestr dostawców modeli'));
  }
  deleteProvider(): Promise<void> {
    return Promise.reject(unsupported('Rejestr dostawców modeli'));
  }
  testProvider(): Promise<ProviderTestResult> {
    return Promise.reject(unsupported('Rejestr dostawców modeli'));
  }
  listAssignments(): Promise<PipelineAssignment[]> {
    return Promise.resolve([]);
  }
  updateAssignment(): Promise<PipelineAssignment> {
    return Promise.reject(unsupported('Rejestr dostawców modeli'));
  }
  listChannels(): Promise<ChannelInfo[]> {
    return Promise.resolve([]);
  }
  updateChannel(): Promise<ChannelInfo> {
    return Promise.reject(unsupported('Kanały'));
  }
  listSecurityEvents(): Promise<SecurityEvent[]> {
    return Promise.resolve([]);
  }
  getAlertRules(): Promise<AlertRules> {
    return Promise.reject(unsupported('Reguły alertów (wersja demo)'));
  }
  updateAlertRules(): Promise<AlertRules> {
    return Promise.reject(unsupported('Reguły alertów (wersja demo)'));
  }
  getPrivacy(): Promise<PrivacySettings> {
    return Promise.reject(unsupported('Ustawienia prywatności'));
  }
  updatePrivacy(): Promise<PrivacySettings> {
    return Promise.reject(unsupported('Ustawienia prywatności'));
  }
  purgeDemoData(): Promise<{ deletedChecks: number }> {
    return Promise.reject(unsupported('Dane demo'));
  }
}
