/**
 * In-browser data source for demos and front-end development. It implements
 * the same `AdminApi` contract as the HTTP client, including permission
 * checks, so switching `dataSource` to `http` needs no change in the pages.
 *
 * Changes made in the panel are kept in localStorage for a few hours, then
 * the example data is regenerated.
 */
import { can, type Permission } from '../../auth/permissions.ts';
import { type AdminApi, ApiError, unsupported } from '../AdminApi.ts';
import type {
  Alert,
  AlertQuery,
  AlertRules,
  AlertType,
  ApiCapabilities,
  AvailableModels,
  CheckFlag,
  ConfigChange,
  EndUser,
  EndUserDetail,
  Feature,
  PurgeResult,
  RuntimeConfig,
  TechEvent,
  TechSummary,
  ThreatReport,
  TrustedSite,
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
  Notification,
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
  UserRef,
  Verdict,
} from '../types.ts';
import { buildClusters, DEFAULT_RECIPIENT_ROLE, detectAlerts, matchRiskTopics } from './detection.ts';
import {
  DEMO_PASSWORD,
  defaultAlertRules,
  defaultPrivacy,
  seedAssignments,
  seedAudit,
  seedCases,
  seedChannels,
  seedChecks,
  seedProviders,
  seedQuality,
  seedSecurityEvents,
  seedSources,
  seedUsers,
  TOPICS,
} from './seed.ts';

const STORAGE_KEY = 'prawdowid-admin-mock-v1';
const ROLE_PL: Record<Role, string> = { admin: 'administrator', moderator: 'moderator', analyst: 'analityk', user: 'użytkownik serwisu' };
const STATUS_PL: Record<string, string> = {
  new: 'nowa',
  in_progress: 'w toku',
  waiting_for_source: 'oczekuje na źródło',
  resolved: 'rozwiązana',
  rejected: 'odrzucona',
};
const PRIORITY_PL: Record<string, string> = { critical: 'krytyczny', high: 'wysoki', medium: 'średni', low: 'niski' };
const STATE_TTL_MS = 6 * 3_600_000;
const HOUR = 3_600_000;
const SESSION_HOURS = 8;

interface AlertState {
  status: AlertStatus;
  caseId?: string;
  notified: Notification[];
}

interface MockState {
  anchor: number;
  alertState: Record<string, AlertState>;
  cases: ModeratorCase[];
  caseSeq: number;
  sources: Source[];
  providers: ModelProvider[];
  assignments: PipelineAssignment[];
  channels: ChannelInfo[];
  rules: AlertRules;
  privacy: PrivacySettings;
  users: User[];
  audit: AuditEntry[];
  deletedCheckIds: string[];
  purgedAt?: number;
}

function freshState(now: number): MockState {
  return {
    anchor: now,
    alertState: {},
    cases: seedCases(now),
    caseSeq: 12,
    sources: seedSources(now),
    providers: seedProviders(now),
    assignments: seedAssignments(now),
    channels: seedChannels(now),
    rules: defaultAlertRules(),
    privacy: defaultPrivacy(),
    users: seedUsers(now),
    audit: seedAudit(now),
    deletedCheckIds: [],
  };
}

function loadState(): MockState {
  const now = Date.now();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as MockState;
      if (parsed && typeof parsed.anchor === 'number' && now - parsed.anchor < STATE_TTL_MS) return parsed;
    }
  } catch {
    // Storage unavailable or corrupted — start from fresh example data.
  }
  return freshState(now);
}

const clone = <T>(value: T): T => structuredClone(value);
const iso = (ms: number = Date.now()) => new Date(ms).toISOString();
const median = (values: number[]) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};
const percentile = (values: number[], p: number) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
};

const MOCK_FEATURES: Feature[] = [
  'cases',
  'clusters',
  'sources',
  'providers',
  'channels',
  'privacy',
  'securityEvents',
  'alertRules',
  'staffUsers',
  'deleteCheck',
  'checkCost',
  'channelFilter',
  'quality',
];
const MOCK_ALERT_TYPES: AlertType[] = [
  'information_gap',
  'query_surge',
  'high_risk',
  'prompt_injection',
  'incident_match',
  'source_status',
  'system',
];
const MOCK_FLAGS: CheckFlag[] = [
  'prompt_injection',
  'high_risk',
  'pii_masked',
  'archival_material',
  'incident_match',
  'source_status_warning',
  'conflicting_sources',
];

export class MockAdminApi implements AdminApi {
  readonly mode = 'mock' as const;
  readonly target = 'dane przykładowe w przeglądarce';
  readonly capabilities: ApiCapabilities = {
    features: new Set(MOCK_FEATURES),
    alertTypes: MOCK_ALERT_TYPES,
    checkFlags: MOCK_FLAGS,
    checkOutcomes: ['technical_error', 'needs_clarification'],
  };
  private state: MockState;
  private checks: CheckRecord[];
  private security: SecurityEvent[];
  private token: string | null = null;
  private unauthorizedHandler: (() => void) | null = null;

  constructor() {
    this.state = loadState();
    this.checks = seedChecks(this.state.anchor);
    this.security = seedSecurityEvents(this.state.anchor, this.checks);
  }

  // ── plumbing ──────────────────────────────────────────────────────────────

  setToken(token: string | null): void {
    this.token = token;
  }

  onUnauthorized(handler: () => void): void {
    this.unauthorizedHandler = handler;
  }

  private persist(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch {
      // Not persisted (private mode / quota): changes last until reload.
    }
  }

  private async delay<T>(value: T, ms = 120 + Math.random() * 260): Promise<T> {
    await new Promise((resolve) => window.setTimeout(resolve, ms));
    return clone(value);
  }

  private currentUser(): User {
    const [prefix, userId, expiry] = (this.token ?? '').split('.');
    const user = this.state.users.find((u) => u.id === userId && u.active);
    if (prefix !== 'mock' || !user || Number(expiry) < Date.now()) {
      this.unauthorizedHandler?.();
      throw new ApiError('Sesja wygasła. Zaloguj się ponownie.', 401);
    }
    return user;
  }

  private require(permission: Permission): User {
    const user = this.currentUser();
    if (!can(user, permission)) throw new ApiError('Brak uprawnień do tej operacji.', 403);
    return user;
  }

  private audit(actor: string, action: string, target: string, detail?: string): void {
    this.state.audit.unshift({ id: `a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`, at: iso(), actor, action, target, detail });
  }

  private ref(user: User): UserRef {
    return { id: user.id, name: user.name, role: user.role };
  }

  private visibleChecks(): CheckRecord[] {
    const deleted = new Set(this.state.deletedCheckIds);
    const purgedAt = this.state.purgedAt;
    const retentionMs = this.state.privacy.retentionDays * 24 * HOUR;
    const now = Date.now();
    const topics = this.state.rules.highRisk.enabled ? this.state.rules.highRisk.topics : [];
    return this.checks
      .filter((c) => !deleted.has(c.id))
      .filter((c) => purgedAt === undefined || Date.parse(c.createdAt) > purgedAt)
      .filter((c) => now - Date.parse(c.createdAt) <= retentionMs)
      .map((c) => {
        const risk = matchRiskTopics([c.query, c.claims[0]?.text ?? ''], topics).map((t) => t.label);
        if (!risk.length) return c;
        return { ...c, riskTopics: risk, flags: [...new Set([...c.flags, 'high_risk' as const])] };
      });
  }

  private clusters(): QueryCluster[] {
    const metas = TOPICS.map((t) => ({ id: t.id, label: t.label, keywords: t.keywords, missing: t.missing }));
    const clusters = buildClusters(this.visibleChecks(), metas, this.state.rules, Date.now());
    for (const cl of clusters) {
      cl.caseId = this.state.cases.find((c) => c.clusterId === cl.id && !['resolved', 'rejected'].includes(c.status))?.id;
    }
    return clusters;
  }

  private alerts(): Alert[] {
    const checks = this.visibleChecks();
    const clusters = this.clusters();
    const now = Date.now();
    const drafts = detectAlerts(clusters, checks, this.security.filter((e) => now - Date.parse(e.at) <= 7 * 24 * HOUR), this.state.rules, now);
    let changed = false;
    const alerts = drafts.map((draft): Alert => {
      let st = this.state.alertState[draft.id];
      if (!st) {
        // First time this alert is seen: notify the recipients configured *now*.
        const recipients = (this.state.rules.recipients[draft.type] ?? [])
          .map((id) => this.state.users.find((u) => u.id === id && u.active))
          .filter((u): u is User => !!u);
        const notified: Notification[] = recipients.flatMap((u) => [
          { user: this.ref(u), channel: 'panel' as const, at: draft.createdAt },
          ...(this.state.rules.notifyByEmail ? [{ user: this.ref(u), channel: 'email' as const, at: draft.createdAt }] : []),
        ]);
        st = { status: 'new', notified };
        this.state.alertState[draft.id] = st;
        changed = true;
      }
      return {
        ...draft,
        status: st.status,
        caseId: st.caseId,
        notified: st.notified,
        recommendedRole: st.notified.length ? undefined : DEFAULT_RECIPIENT_ROLE[draft.type],
      };
    });
    if (changed) this.persist();
    const sev = { critical: 0, high: 1, medium: 2, low: 3 };
    return alerts.sort((a, b) => sev[a.severity] - sev[b.severity] || b.updatedAt.localeCompare(a.updatedAt));
  }

  private findCase(id: string): ModeratorCase {
    const found = this.state.cases.find((c) => c.id === id);
    if (!found) throw new ApiError('Nie znaleziono sprawy.', 404);
    return found;
  }

  private withLiveCounts(c: ModeratorCase): ModeratorCase {
    if (!c.clusterId) return c;
    const cl = this.clusters().find((x) => x.id === c.clusterId);
    return cl ? { ...c, queryCount: Math.max(c.queryCount, cl.total), riskTopics: cl.riskTopics } : c;
  }

  private caseEvent(c: ModeratorCase, actor: string, kind: ModeratorCase['events'][number]['kind'], text: string): void {
    c.events.push({ id: `ev-${c.events.length + 1}-${Date.now().toString(36)}`, at: iso(), actor, kind, text });
    c.updatedAt = iso();
  }

  // ── auth ──────────────────────────────────────────────────────────────────

  async login(email: string, password: string): Promise<Session> {
    await this.delay(null, 450);
    const user = this.state.users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!user || password !== DEMO_PASSWORD) {
      this.security.unshift({ id: `sec-auth-${Date.now()}`, at: iso(), type: 'auth_failed', channel: 'panel', detail: 'Nieudane logowanie do panelu.', action: 'logged' });
      throw new ApiError('Nieprawidłowy e-mail lub hasło.', 401);
    }
    if (!user.active) throw new ApiError('Konto jest nieaktywne. Skontaktuj się z administratorem.', 403);
    const expiresAt = Date.now() + SESSION_HOURS * HOUR;
    user.lastLoginAt = iso();
    this.audit(user.name, 'Logowanie', 'panel');
    this.persist();
    return clone({ token: `mock.${user.id}.${expiresAt}`, user, expiresAt: iso(expiresAt) });
  }

  async logout(): Promise<void> {
    await this.delay(null, 50);
  }

  async me(): Promise<User> {
    return this.delay(this.currentUser(), 60);
  }

  async health(): Promise<{ status: string; version?: string }> {
    return this.delay({ status: 'ok', version: 'mock' }, 80);
  }

  // ── dashboard ─────────────────────────────────────────────────────────────

  async getDashboard(rangeHours: number): Promise<DashboardStats> {
    this.require('dashboard:read');
    const now = Date.now();
    const inRange = this.visibleChecks().filter((c) => now - Date.parse(c.createdAt) <= rangeHours * HOUR);
    const substantive = inRange.filter((c) => c.outcome === 'verdict' || c.outcome === 'abstained');
    const verdicts: Partial<Record<Verdict, number>> = {};
    const channels: Record<string, number> = {};
    for (const c of inRange) {
      if (c.overallVerdict) verdicts[c.overallVerdict] = (verdicts[c.overallVerdict] ?? 0) + 1;
      channels[c.channel] = (channels[c.channel] ?? 0) + 1;
    }
    const bucketMs = rangeHours <= 48 ? HOUR : 24 * HOUR;
    const buckets = Math.ceil((rangeHours * HOUR) / bucketMs);
    const series = Array.from({ length: buckets }, (_, i) => ({
      t: iso(now - (buckets - i) * bucketMs),
      total: 0,
      abstained: 0,
    }));
    for (const c of inRange) {
      const idx = buckets - 1 - Math.floor((now - Date.parse(c.createdAt)) / bucketMs);
      if (idx < 0 || idx >= buckets) continue;
      series[idx].total += 1;
      if (c.outcome === 'abstained') series[idx].abstained += 1;
    }
    const alerts = this.alerts().filter((a) => ['new', 'acknowledged', 'escalated'].includes(a.status));
    const cost = inRange.reduce((sum, c) => sum + c.costPln, 0);
    const latencies = substantive.map((c) => c.durationMs);
    return this.delay({
      rangeHours,
      generatedAt: iso(now),
      checks: inRange.length,
      abstained: inRange.filter((c) => c.outcome === 'abstained').length,
      technicalErrors: inRange.filter((c) => c.outcome === 'technical_error').length,
      injectionsBlocked: inRange.filter((c) => c.flags.includes('prompt_injection')).length,
      medianLatencyMs: Math.round(median(latencies)),
      p95LatencyMs: Math.round(percentile(latencies, 95)),
      costTotalPln: Number(cost.toFixed(2)),
      costPer1000Pln: inRange.length ? Number(((cost / inRange.length) * 1000).toFixed(2)) : 0,
      verdicts,
      channels,
      series,
      openCases: this.state.cases.filter((c) => !['resolved', 'rejected'].includes(c.status)).length,
      activeAlerts: alerts.length,
      criticalAlerts: alerts.filter((a) => a.severity === 'critical').length,
      informationGaps: this.clusters().filter((c) => c.isInformationGap).length,
      quality: seedQuality(),
      qualityEvaluatedAt: iso(this.state.anchor - 7 * HOUR),
    });
  }

  // ── alerts ────────────────────────────────────────────────────────────────

  async listAlerts(query: AlertQuery = {}): Promise<Alert[]> {
    this.require('alerts:read');
    const list = this.alerts().filter((a) => {
      if (query.type && query.type !== 'any' && a.type !== query.type) return false;
      if (query.severity && query.severity !== 'any' && a.severity !== query.severity) return false;
      if (query.status === 'open') return ['new', 'acknowledged', 'escalated'].includes(a.status);
      if (query.status && query.status !== 'any' && a.status !== query.status) return false;
      return true;
    });
    return this.delay(list);
  }

  async updateAlert(id: string, patch: { status: AlertStatus }): Promise<Alert> {
    const user = this.require('alerts:write');
    const st = this.state.alertState[id];
    const alert = this.alerts().find((a) => a.id === id);
    if (!st || !alert) throw new ApiError('Nie znaleziono alertu.', 404);
    st.status = patch.status;
    this.audit(user.name, 'Zmiana statusu alertu', alert.title, patch.status);
    this.persist();
    return this.delay({ ...alert, status: patch.status });
  }

  async escalateAlert(id: string, assigneeId?: string): Promise<ModeratorCase> {
    const user = this.require('cases:write');
    const alert = this.alerts().find((a) => a.id === id);
    if (!alert) throw new ApiError('Nie znaleziono alertu.', 404);
    const cluster = alert.clusterId ? this.clusters().find((c) => c.id === alert.clusterId) : undefined;
    const assignee = assigneeId ? this.state.users.find((u) => u.id === assigneeId) : undefined;

    // One case per group of similar questions: reuse an open case if there is one.
    let target = this.state.cases.find(
      (c) => (alert.clusterId && c.clusterId === alert.clusterId && !['resolved', 'rejected'].includes(c.status)) || c.alertIds.includes(alert.id),
    );
    if (target) {
      if (!target.alertIds.includes(alert.id)) target.alertIds.push(alert.id);
      target.checkIds = [...new Set([...target.checkIds, ...alert.checkIds])];
      target.queryCount = Math.max(target.queryCount, cluster?.total ?? target.checkIds.length);
      this.caseEvent(target, user.name, 'queries_linked', `Dołączono alert „${alert.title}” — sprawa zaktualizowana, bez tworzenia duplikatu.`);
    } else {
      this.state.caseSeq += 1;
      const role = DEFAULT_RECIPIENT_ROLE[alert.type];
      target = {
        id: `CASE-${String(this.state.caseSeq).padStart(4, '0')}`,
        title: cluster?.label ?? alert.title,
        status: 'new',
        priority: alert.severity,
        clusterId: alert.clusterId,
        alertIds: [alert.id],
        checkIds: [...alert.checkIds],
        queryCount: cluster?.total ?? alert.checkIds.length,
        forwarding: {
          recommended: true,
          recommendedRole: role,
          reason: `${alert.rule}.`,
        },
        riskTopics: cluster?.riskTopics ?? [],
        createdAt: iso(),
        updatedAt: iso(),
        events: [],
      };
      this.caseEvent(target, user.name, 'created', `Sprawa utworzona z alertu „${alert.title}”.`);
      this.caseEvent(target, 'System', 'forward_recommended', `Rekomendacja: przekazać do roli „${ROLE_PL[role]}”. Nic nie zostało jeszcze wysłane.`);
      this.state.cases.unshift(target);
    }
    if (assignee) {
      target.assignee = this.ref(assignee);
      this.caseEvent(target, user.name, 'assigned', `Osoba prowadząca: ${assignee.name}.`);
    }
    const st = this.state.alertState[alert.id];
    st.status = 'escalated';
    st.caseId = target.id;
    this.audit(user.name, 'Eskalacja alertu do sprawy', target.id, alert.title);
    this.persist();
    return this.delay(this.withLiveCounts(target));
  }

  // ── clusters ──────────────────────────────────────────────────────────────

  async listClusters(query: ClusterQuery = {}): Promise<QueryCluster[]> {
    this.require('clusters:read');
    const q = query.search?.trim().toLowerCase();
    const list = this.clusters().filter(
      (c) =>
        (!query.onlyGaps || c.isInformationGap || c.noEvidenceRatio >= 0.5) &&
        (!query.onlySurging || c.isSurging) &&
        (!q || c.label.toLowerCase().includes(q) || c.keywords.some((k) => k.toLowerCase().includes(q))),
    );
    return this.delay(list);
  }

  async getCluster(id: string): Promise<QueryCluster> {
    this.require('clusters:read');
    const cl = this.clusters().find((c) => c.id === id);
    if (!cl) throw new ApiError('Nie znaleziono grupy zapytań.', 404);
    return this.delay(cl);
  }

  // ── cases ─────────────────────────────────────────────────────────────────

  async listCases(query: CaseQuery = {}): Promise<ModeratorCase[]> {
    this.require('cases:read');
    const q = query.search?.trim().toLowerCase();
    const list = this.state.cases
      .filter((c) => {
        if (query.status === 'open') return !['resolved', 'rejected'].includes(c.status);
        if (query.status && query.status !== 'any') return c.status === query.status;
        return true;
      })
      .filter((c) => !q || c.title.toLowerCase().includes(q) || c.id.toLowerCase().includes(q))
      .map((c) => this.withLiveCounts(c))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    return this.delay(list);
  }

  async getCase(id: string): Promise<ModeratorCase> {
    this.require('cases:read');
    return this.delay(this.withLiveCounts(this.findCase(id)));
  }

  async updateCase(id: string, patch: CasePatch): Promise<ModeratorCase> {
    const user = this.require('cases:write');
    const c = this.findCase(id);
    if (patch.status && patch.status !== c.status) {
      if ((patch.status === 'resolved' || patch.status === 'rejected') && !(patch.resolution ?? c.resolution)?.trim()) {
        throw new ApiError('Zamknięcie sprawy wymaga opisu rozstrzygnięcia.', 422);
      }
      c.status = patch.status;
      this.caseEvent(c, user.name, 'status_changed', `Status: ${STATUS_PL[patch.status]}.`);
    }
    if (patch.resolution !== undefined) c.resolution = patch.resolution;
    if (patch.priority && patch.priority !== c.priority) {
      c.priority = patch.priority;
      this.caseEvent(c, user.name, 'status_changed', `Priorytet: ${PRIORITY_PL[patch.priority]}.`);
    }
    if (patch.assigneeId !== undefined) {
      const assignee = patch.assigneeId ? this.state.users.find((u) => u.id === patch.assigneeId) : undefined;
      c.assignee = assignee ? this.ref(assignee) : undefined;
      this.caseEvent(c, user.name, 'assigned', assignee ? `Osoba prowadząca: ${assignee.name}.` : 'Usunięto osobę prowadzącą.');
    }
    this.audit(user.name, 'Aktualizacja sprawy', c.id);
    this.persist();
    return this.delay(this.withLiveCounts(c));
  }

  async addCaseComment(id: string, text: string): Promise<ModeratorCase> {
    const user = this.require('cases:write');
    const c = this.findCase(id);
    if (!text.trim()) throw new ApiError('Komentarz nie może być pusty.', 422);
    this.caseEvent(c, user.name, 'comment', text.trim().slice(0, 2000));
    this.persist();
    return this.delay(this.withLiveCounts(c));
  }

  async forwardCase(id: string, userId: string, note?: string): Promise<ModeratorCase> {
    const user = this.require('cases:forward');
    const c = this.findCase(id);
    const recipient = this.state.users.find((u) => u.id === userId && u.active);
    if (!recipient) throw new ApiError('Wybrany użytkownik nie istnieje lub jest nieaktywny.', 422);
    c.forwarding = { ...c.forwarding, forwardedTo: this.ref(recipient), forwardedAt: iso(), forwardedBy: user.name };
    if (c.status === 'new') c.status = 'in_progress';
    this.caseEvent(c, user.name, 'forwarded', `Przekazano: ${recipient.name} (${ROLE_PL[recipient.role]}).${note?.trim() ? ` Notatka: ${note.trim()}` : ''}`);
    this.audit(user.name, 'Przekazanie sprawy', c.id, recipient.name);
    this.persist();
    return this.delay(this.withLiveCounts(c));
  }

  // ── checks ────────────────────────────────────────────────────────────────

  async listChecks(query: CheckQuery = {}): Promise<Page<CheckRecord>> {
    this.require('checks:read');
    const now = Date.now();
    const q = query.search?.trim().toLowerCase();
    const filtered = this.visibleChecks().filter((c) => {
      if (q && !c.query.toLowerCase().includes(q) && !c.id.includes(q)) return false;
      if (query.outcome && query.outcome !== 'any' && c.outcome !== query.outcome) return false;
      if (query.verdict && query.verdict !== 'any' && c.overallVerdict !== query.verdict) return false;
      if (query.channel && query.channel !== 'any' && c.channel !== query.channel) return false;
      if (query.flag && query.flag !== 'any' && !c.flags.includes(query.flag)) return false;
      if (query.clusterId && c.clusterId !== query.clusterId) return false;
      if (query.sinceHours && now - Date.parse(c.createdAt) > query.sinceHours * HOUR) return false;
      return true;
    });
    const pageSize = query.pageSize ?? 25;
    const page = Math.max(1, query.page ?? 1);
    return this.delay({ items: filtered.slice((page - 1) * pageSize, page * pageSize), total: filtered.length, page, pageSize });
  }

  async getCheck(id: string): Promise<CheckRecord> {
    this.require('checks:read');
    const found = this.visibleChecks().find((c) => c.id === id);
    if (!found) throw new ApiError('Nie znaleziono zapisu sprawdzenia (mógł zostać usunięty).', 404);
    return this.delay(found);
  }

  async deleteCheck(id: string): Promise<void> {
    const user = this.require('checks:delete');
    this.state.deletedCheckIds.push(id);
    this.audit(user.name, 'Usunięcie zapisu sprawdzenia', id, 'Żądanie usunięcia danych');
    this.persist();
    await this.delay(null);
  }

  // ── sources ───────────────────────────────────────────────────────────────

  async listSources(): Promise<Source[]> {
    this.require('sources:read');
    return this.delay(this.state.sources);
  }

  async createSource(input: SourceInput): Promise<Source> {
    const user = this.require('sources:write');
    let url: URL;
    try {
      url = new URL(input.url);
    } catch {
      throw new ApiError('Nieprawidłowy adres URL źródła.', 422);
    }
    if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new ApiError('Dozwolone są tylko adresy http(s).', 422);
    const domain = url.hostname.replace(/^www\./, '');
    if (this.state.sources.some((s) => s.url === input.url)) throw new ApiError('To źródło jest już w katalogu.', 409);
    const source: Source = {
      ...input,
      id: `src-${domain.replace(/[^a-z0-9]+/gi, '-')}-${Date.now().toString(36)}`,
      domain,
      status: 'active',
      documents: 0,
      addedAt: iso(),
      lastFetchOk: true,
    };
    this.state.sources.push(source);
    this.audit(user.name, 'Dodanie źródła', source.name, input.qualification);
    this.persist();
    return this.delay(source);
  }

  async updateSource(id: string, patch: SourcePatch): Promise<Source> {
    const user = this.require('sources:write');
    const source = this.state.sources.find((s) => s.id === id);
    if (!source) throw new ApiError('Nie znaleziono źródła.', 404);
    if (patch.status && patch.status !== 'active' && !patch.statusNote?.trim()) {
      throw new ApiError('Zawieszenie lub wykluczenie wymaga uzasadnienia.', 422);
    }
    Object.assign(source, patch);
    if (patch.status === 'active') source.statusNote = undefined;
    const action = patch.status === 'excluded' ? 'Wykluczenie źródła' : patch.status === 'suspended' ? 'Zawieszenie źródła' : patch.status === 'active' ? 'Przywrócenie źródła' : 'Zmiana źródła';
    this.audit(user.name, action, source.name, patch.statusNote);
    this.persist();
    return this.delay(source);
  }

  async refreshSource(id: string): Promise<Source> {
    const user = this.require('sources:write');
    const source = this.state.sources.find((s) => s.id === id);
    if (!source) throw new ApiError('Nie znaleziono źródła.', 404);
    await new Promise((resolve) => window.setTimeout(resolve, 700));
    const ok = source.id !== 'src-voivode';
    source.lastFetchedAt = iso();
    source.lastFetchOk = ok;
    if (ok && source.status === 'active') source.documents += Math.floor(Math.random() * 4);
    this.audit(user.name, 'Odświeżenie źródła', source.name, ok ? 'OK' : 'HTTP 503');
    this.persist();
    if (!ok) throw new ApiError('Nie udało się pobrać źródła (HTTP 503). Źródło pozostaje zawieszone.', 502);
    return this.delay(source);
  }

  // ── models ────────────────────────────────────────────────────────────────

  async listProviders(): Promise<ModelProvider[]> {
    this.require('models:read');
    return this.delay(this.state.providers);
  }

  async createProvider(input: ProviderInput): Promise<ModelProvider> {
    const user = this.require('models:write');
    if (!input.name.trim() || !input.model.trim()) throw new ApiError('Nazwa i identyfikator modelu są wymagane.', 422);
    if (!input.roles.length) throw new ApiError('Wybierz co najmniej jedno zastosowanie modelu.', 422);
    if (input.keyRef && !/^[A-Z][A-Z0-9_]{2,63}$/.test(input.keyRef)) {
      throw new ApiError('Nazwa sekretu: wielkie litery, cyfry i _ (np. MISTRAL_API_KEY).', 422);
    }
    const provider: ModelProvider = {
      ...input,
      id: `p-${input.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 24)}-${Date.now().toString(36)}`,
      // A new key is added to the server-side secret store, never through the panel.
      keyConfigured: !input.keyRef,
      health: 'unknown',
    };
    this.state.providers.push(provider);
    this.audit(user.name, 'Dodanie dostawcy modelu', provider.name, `${provider.model} · ${provider.region}`);
    this.persist();
    return this.delay(provider);
  }

  async deleteProvider(id: string): Promise<void> {
    const user = this.require('models:write');
    const used = this.state.assignments.some((a) => a.providerId === id || a.fallbackProviderIds.includes(id));
    if (used) throw new ApiError('Dostawca jest używany w potoku. Najpierw zmień przypisanie.', 409);
    const provider = this.state.providers.find((p) => p.id === id);
    this.state.providers = this.state.providers.filter((p) => p.id !== id);
    this.audit(user.name, 'Usunięcie dostawcy modelu', provider?.name ?? id);
    this.persist();
    await this.delay(null);
  }

  async testProvider(id: string): Promise<ProviderTestResult> {
    const user = this.require('models:read');
    const provider = this.state.providers.find((p) => p.id === id);
    if (!provider) throw new ApiError('Nie znaleziono dostawcy.', 404);
    await new Promise((resolve) => window.setTimeout(resolve, 600 + Math.random() * 600));
    let result: ProviderTestResult;
    if (!provider.keyConfigured) {
      result = { ok: false, latencyMs: 0, message: `Brak klucza w magazynie sekretów (${provider.keyRef}). Dostawca nie może zostać użyty.` };
    } else if (provider.health === 'down') {
      result = { ok: false, latencyMs: 10_000, message: 'Brak odpowiedzi w ciągu 10 s (timeout).' };
    } else {
      const latency = Math.round((provider.latencyP50Ms ?? 500) * (0.8 + Math.random() * 0.5));
      result = { ok: true, latencyMs: latency, message: provider.health === 'degraded' ? 'Odpowiedź poprawna, ale podwyższony odsetek błędów.' : 'Połączenie poprawne, odpowiedź zgodna ze schematem.' };
    }
    provider.lastCheckedAt = iso();
    this.audit(user.name, 'Test połączenia z modelem', provider.name, result.message);
    this.persist();
    return clone(result);
  }

  async listAssignments(): Promise<PipelineAssignment[]> {
    this.require('models:read');
    return this.delay(this.state.assignments);
  }

  async updateAssignment(role: PipelineRole, patch: AssignmentPatch): Promise<PipelineAssignment> {
    const user = this.require('models:write');
    const assignment = this.state.assignments.find((a) => a.role === role);
    if (!assignment) throw new ApiError('Nieznany etap potoku.', 404);
    const nameOf = (id: string | null) => (id ? (this.state.providers.find((p) => p.id === id)?.model ?? id) : 'brak');
    for (const pid of [patch.providerId, ...(patch.fallbackProviderIds ?? [])]) {
      if (!pid) continue;
      const provider = this.state.providers.find((p) => p.id === pid);
      if (!provider) throw new ApiError('Nie znaleziono dostawcy.', 404);
      if (!provider.roles.includes(role)) throw new ApiError(`Model ${provider.model} nie obsługuje tego etapu.`, 422);
      if (!provider.keyConfigured) throw new ApiError(`Nie można użyć ${provider.name}: brak klucza API (${provider.keyRef}).`, 422);
    }
    const before = nameOf(assignment.providerId);
    if (patch.providerId !== undefined) assignment.providerId = patch.providerId;
    if (patch.fallbackProviderIds) assignment.fallbackProviderIds = patch.fallbackProviderIds.filter((id) => id !== assignment.providerId);
    if (patch.enabled !== undefined) assignment.enabled = patch.enabled;
    if (patch.params) assignment.params = { ...assignment.params, ...patch.params };
    assignment.updatedAt = iso();
    assignment.updatedBy = user.name;
    const detail = patch.providerId !== undefined ? `${before} → ${nameOf(assignment.providerId)}` : 'Zmiana parametrów / zapasowych modeli';
    this.audit(user.name, 'Zmiana modelu', role, detail);
    this.persist();
    return this.delay(assignment);
  }

  // ── channels ──────────────────────────────────────────────────────────────

  async listChannels(): Promise<ChannelInfo[]> {
    this.require('dashboard:read');
    const now = Date.now();
    const recent = this.visibleChecks().filter((c) => now - Date.parse(c.createdAt) <= 24 * HOUR);
    const list = this.state.channels.map((ch) => {
      const mine = recent.filter((c) => c.channel === ch.id);
      return { ...ch, requests24h: mine.length, medianLatencyMs: Math.round(median(mine.map((c) => c.durationMs))) };
    });
    return this.delay(list);
  }

  async updateChannel(id: string, patch: { enabled: boolean }): Promise<ChannelInfo> {
    const user = this.require('channels:write');
    const ch = this.state.channels.find((c) => c.id === id);
    if (!ch) throw new ApiError('Nie znaleziono kanału.', 404);
    ch.enabled = patch.enabled;
    this.audit(user.name, patch.enabled ? 'Włączenie kanału' : 'Wyłączenie kanału', ch.name);
    this.persist();
    return this.delay(ch);
  }

  // ── security ──────────────────────────────────────────────────────────────

  async listSecurityEvents(sinceHours = 168): Promise<SecurityEvent[]> {
    this.require('security:read');
    const now = Date.now();
    return this.delay(this.security.filter((e) => now - Date.parse(e.at) <= sinceHours * HOUR));
  }

  // ── settings ──────────────────────────────────────────────────────────────

  async getAlertRules(): Promise<AlertRules> {
    this.require('rules:read');
    return this.delay(this.state.rules);
  }

  async updateAlertRules(rules: AlertRules): Promise<AlertRules> {
    const user = this.require('rules:write');
    const g = rules.informationGap;
    const s = rules.querySurge;
    if (g.minQueries < 1 || g.windowHours < 1 || g.minNoEvidenceRatio < 0 || g.minNoEvidenceRatio > 1) {
      throw new ApiError('Nieprawidłowe progi reguły luki informacyjnej.', 422);
    }
    if (s.minQueries < 1 || s.windowHours < 1 || s.growthFactor < 1) {
      throw new ApiError('Nieprawidłowe progi reguły wzrostu zapytań.', 422);
    }
    if (rules.highRisk.topics.some((t) => !t.label.trim() || !t.keywords.length)) {
      throw new ApiError('Każdy temat wysokiego ryzyka musi mieć nazwę i co najmniej jedno słowo kluczowe.', 422);
    }
    this.state.rules = clone(rules);
    this.audit(user.name, 'Zmiana reguł alertów', 'Reguły alertów i powiadomień');
    this.persist();
    return this.delay(this.state.rules);
  }

  async getPrivacy(): Promise<PrivacySettings> {
    this.require('settings:read');
    return this.delay(this.state.privacy);
  }

  async updatePrivacy(settings: PrivacySettings): Promise<PrivacySettings> {
    const user = this.require('settings:write');
    if (settings.retentionDays < 1 || settings.retentionDays > 365) throw new ApiError('Okres retencji: od 1 do 365 dni.', 422);
    this.state.privacy = clone(settings);
    this.audit(user.name, 'Zmiana ustawień prywatności', 'Prywatność i retencja', `retencja ${settings.retentionDays} dni`);
    this.persist();
    return this.delay(this.state.privacy);
  }

  async purgeDemoData(): Promise<{ deletedChecks: number }> {
    const user = this.require('settings:write');
    const count = this.visibleChecks().length;
    this.state.purgedAt = Date.now();
    this.audit(user.name, 'Usunięcie danych sesji demonstracyjnej', 'Historia weryfikacji', `${count} zapisów`);
    this.persist();
    return this.delay({ deletedChecks: count });
  }

  /** Demo only: wipe stored changes and regenerate the example data. */
  resetDemo(): void {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }

  // ── users ─────────────────────────────────────────────────────────────────

  async listUsers(): Promise<User[]> {
    this.require('cases:read');
    return this.delay(this.state.users);
  }

  async createUser(input: { email: string; name: string; role: Role }): Promise<User> {
    const actor = this.require('users:write');
    const email = input.email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new ApiError('Nieprawidłowy adres e-mail.', 422);
    if (!input.name.trim()) throw new ApiError('Imię i nazwisko są wymagane.', 422);
    if (this.state.users.some((u) => u.email === email)) throw new ApiError('Użytkownik o tym adresie już istnieje.', 409);
    const user: User = { id: `u-${Date.now().toString(36)}`, email, name: input.name.trim(), role: input.role, active: true, createdAt: iso() };
    this.state.users.push(user);
    this.audit(actor.name, 'Dodanie użytkownika', user.email, input.role);
    this.persist();
    return this.delay(user);
  }

  async updateUser(id: string, patch: { role?: Role; active?: boolean }): Promise<User> {
    const actor = this.require('users:write');
    const user = this.state.users.find((u) => u.id === id);
    if (!user) throw new ApiError('Nie znaleziono użytkownika.', 404);
    if (user.id === actor.id && (patch.active === false || (patch.role && patch.role !== 'admin'))) {
      throw new ApiError('Nie możesz odebrać uprawnień administratora samemu sobie ani dezaktywować własnego konta.', 422);
    }
    Object.assign(user, patch);
    this.audit(actor.name, 'Zmiana użytkownika', user.email, JSON.stringify(patch));
    this.persist();
    return this.delay(user);
  }

  async listAudit(): Promise<AuditEntry[]> {
    this.require('audit:read');
    return this.delay(this.state.audit);
  }

  // ── backend/admin only: not part of the demo data ─────────────────────────

  changeOwnPassword(): Promise<void> {
    return Promise.reject(unsupported('Zmiana hasła'));
  }
  resetUserPassword(): Promise<void> {
    return Promise.reject(unsupported('Zmiana hasła'));
  }

  listEndUsers(): Promise<EndUser[]> {
    return Promise.reject(unsupported('Użytkownicy serwisu'));
  }
  getEndUser(): Promise<EndUserDetail> {
    return Promise.reject(unsupported('Użytkownicy serwisu'));
  }
  blockEndUser(): Promise<EndUser> {
    return Promise.reject(unsupported('Blokada użytkownika'));
  }
  unblockEndUser(): Promise<EndUser> {
    return Promise.reject(unsupported('Blokada użytkownika'));
  }
  updateGapStatus(): Promise<QueryCluster> {
    return Promise.reject(unsupported('Stan luki informacyjnej'));
  }
  getRuntimeConfig(): Promise<RuntimeConfig> {
    return Promise.reject(unsupported('Konfiguracja backendu'));
  }
  updateRuntimeConfig(): Promise<{ changes: ConfigChange[]; config: RuntimeConfig }> {
    return Promise.reject(unsupported('Konfiguracja backendu'));
  }
  listAvailableModels(): Promise<AvailableModels> {
    return Promise.reject(unsupported('Lista modeli'));
  }
  listTechEvents(): Promise<{ file: string; items: TechEvent[] }> {
    return Promise.reject(unsupported('Logi techniczne'));
  }
  getTechSummary(): Promise<TechSummary> {
    return Promise.reject(unsupported('Logi techniczne'));
  }
  getThreats(): Promise<ThreatReport> {
    return Promise.reject(unsupported('Zagrożenia z logów'));
  }
  listTrustedSites(): Promise<TrustedSite[]> {
    return Promise.reject(unsupported('Strony zaufane'));
  }
  createTrustedSite(): Promise<TrustedSite> {
    return Promise.reject(unsupported('Strony zaufane'));
  }
  updateTrustedSite(): Promise<TrustedSite> {
    return Promise.reject(unsupported('Strony zaufane'));
  }
  deleteTrustedSite(): Promise<void> {
    return Promise.reject(unsupported('Strony zaufane'));
  }
  checkTrustedSite(): Promise<TrustedSite> {
    return Promise.reject(unsupported('Strony zaufane'));
  }
  purgeOldData(): Promise<PurgeResult> {
    return Promise.reject(unsupported('Retencja danych'));
  }
}
