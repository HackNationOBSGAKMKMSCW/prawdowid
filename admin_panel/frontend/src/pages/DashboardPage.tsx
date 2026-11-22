import { Link, useNavigate } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { Alert, ModelProvider, ModeratorCase, PipelineAssignment, QueryCluster, Source } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon, type IconName } from '../components/icons.tsx';
import { ALERT_TYPE, HEALTH, PIPELINE_ROLE, ROLE_LABEL, SEVERITY, type Tone } from '../components/labels.ts';
import { useRefreshCounts } from '../components/Layout.tsx';
import { Async, Badge, Card, EmptyState, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDuration, fmtInt, fmtPct, fmtRelative, plural } from '../utils/format.ts';

const URGENT = new Set(['critical', 'high']);

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5 || h >= 18) return 'Dobry wieczór';
  return 'Dzień dobry';
}

/** What a case is waiting for, in plain words. */
function caseNeed(c: ModeratorCase): string | null {
  if (!c.assignee) return 'Nikt jej nie prowadzi';
  if (c.forwarding.recommended && !c.forwarding.forwardedTo) return 'Czeka na przekazanie';
  if (c.status === 'new') return 'Nierozpoczęta';
  return null;
}

export default function DashboardPage() {
  const api = getApi();
  const { user, can } = useAuth();
  const navigate = useNavigate();
  const refreshCounts = useRefreshCounts();
  const { run, busy } = useAction();

  const withCases = supports('cases');
  const lifecycle = supports('gapLifecycle');
  const alerts = useAsync(() => api.listAlerts({ status: 'open' }), []);
  const gaps = useAsync(() => api.listClusters({ onlyGaps: true }), []);
  const cases = useAsync(() => (withCases ? api.listCases({ status: 'open' }) : Promise.resolve([])), []);
  const stats = useAsync(() => api.getDashboard(24), []);
  const sources = useAsync<Source[]>(() => (supports('sources') ? api.listSources() : Promise.resolve([])), []);
  const models = useAsync<{ providers: ModelProvider[]; assignments: PipelineAssignment[] } | null>(
    () =>
      can('models:read') && supports('providers')
        ? Promise.all([api.listProviders(), api.listAssignments()]).then(([providers, assignments]) => ({ providers, assignments }))
        : Promise.resolve(null),
    [],
  );

  const openAlerts = alerts.data ?? [];
  const urgent = openAlerts.filter((a) => URGENT.has(a.severity) && a.status !== 'escalated');
  const critical = openAlerts.filter((a) => a.severity === 'critical' && a.status === 'new');
  // Gaps nobody has picked up yet: without a case (mock) or still `active`, not `in_progress` (backend).
  const gapsWithoutCase = (gaps.data ?? []).filter((g) =>
    lifecycle ? g.gapStatus === 'active' : g.isInformationGap && !g.caseId,
  );
  const waitingCases = (cases.data ?? []).filter((c) => caseNeed(c));

  const modelProblems = (models.data?.assignments ?? [])
    .filter((a) => a.enabled && a.providerId)
    .map((a) => ({ a, p: models.data?.providers.find((p) => p.id === a.providerId) }))
    .filter((x): x is { a: PipelineAssignment; p: ModelProvider } => !!x.p && x.p.health !== 'ok');
  const sourceProblems = (sources.data ?? []).filter((s) => s.status !== 'excluded' && !s.lastFetchOk);
  const systemIssues = modelProblems.length + sourceProblems.length + (stats.data?.technicalErrors ? 1 : 0);

  const reloadAll = () => {
    alerts.reload();
    gaps.reload();
    cases.reload();
    refreshCounts();
  };

  const escalate = async (alertId: string) => {
    let id = '';
    const ok = await run(async () => {
      id = (await api.escalateAlert(alertId)).id;
    }, 'Sprawa utworzona.');
    if (ok) {
      refreshCounts();
      navigate(`/cases/${id}`);
    }
  };

  const acknowledge = async (a: Alert) => {
    if (await run(() => api.updateAlert(a.id, { status: 'acknowledged' }), 'Alert przyjęty.')) reloadAll();
  };

  const firstName = user?.name.split(' ')[0] ?? '';
  const blockedUsers = stats.data?.blockedUsers ?? 0;
  const allClear = critical.length + urgent.length + gapsWithoutCase.length + waitingCases.length + systemIssues === 0;

  return (
    <>
      <div className="hello">
        <div>
          <h1>
            {greeting()}
            {firstName && user?.name !== 'Administrator systemu' ? `, ${firstName}` : ''}
          </h1>
          <p className="page-desc">
            {alerts.loading
              ? 'Sprawdzam, co wymaga uwagi…'
              : allClear
                ? 'Wszystko pod kontrolą — nie ma nic pilnego.'
                : 'Oto sprawy, które wymagają Twojej uwagi. Najpilniejsze są na górze.'}
          </p>
        </div>
        <Link to="/stats" className="btn btn-sm">
          <Icon name="chart" size={16} /> Statystyki
        </Link>
      </div>

      <div className="att-grid">
        <AttentionTile to="/alerts" icon="alert" tone="critical" count={critical.length} label="Krytyczne alerty" ok="Brak krytycznych alertów" />
        <AttentionTile to="/alerts" icon="bell" tone="serious" count={urgent.length} label="Pilne do przejrzenia" ok="Nic pilnego" />
        {lifecycle ? (
          <AttentionTile to="/gaps" icon="gap" tone="warning" count={gapsWithoutCase.length} label={plural(gapsWithoutCase.length, ['luka czeka', 'luki czekają', 'luk czeka'])} ok="Luki są obsługiwane" />
        ) : (
          <AttentionTile to="/gaps" icon="gap" tone="warning" count={gapsWithoutCase.length} label={plural(gapsWithoutCase.length, ['luka bez sprawy', 'luki bez sprawy', 'luk bez sprawy'])} ok="Luki mają sprawy" />
        )}
        {withCases ? (
          <AttentionTile to="/cases" icon="folder" tone="warning" count={waitingCases.length} label={plural(waitingCases.length, ['sprawa czeka', 'sprawy czekają', 'spraw czeka'])} ok="Sprawy są w toku" />
        ) : (
          supports('endUsers') && (
            <AttentionTile to="/end-users" icon="lock" tone="warning" count={blockedUsers} label={plural(blockedUsers, ['zablokowany użytkownik', 'zablokowanych użytkowników', 'zablokowanych użytkowników'])} ok="Nikt nie jest zablokowany" />
          )
        )}
        <AttentionTile
          to={supports('providers') && can('models:read') ? '/models' : supports('techEvents') ? '/logs' : supports('sources') ? '/sources' : '/checks'}
          icon="plug"
          tone="warning"
          count={systemIssues}
          label="Problemy techniczne"
          ok="System działa"
        />
      </div>

      <div className="grid-2-1">
        <Card
          title="Pilne alerty"
          subtitle={withCases ? 'Krytyczne i wysokie, jeszcze bez sprawy.' : 'Krytyczne i wysokie, jeszcze otwarte.'}
          actions={
            <Link to="/alerts" className="btn btn-sm btn-ghost">
              Wszystkie <Icon name="arrowRight" size={14} />
            </Link>
          }
          padded={false}
        >
          <Async state={alerts}>
            {() =>
              urgent.length === 0 ? (
                <EmptyState title="Brak pilnych alertów" icon="check">
                  Nowe alerty pojawią się tutaj automatycznie.
                </EmptyState>
              ) : (
                <ul className="todo-list">
                  {urgent.slice(0, 6).map((a) => (
                    <li key={a.id} className={`todo sev-${a.severity}`}>
                      <div className="todo-main">
                        <div className="row gap-sm wrap">
                          <Badge tone={SEVERITY[a.severity].tone}>{SEVERITY[a.severity].label}</Badge>
                          <span className="muted small">
                            {ALERT_TYPE[a.type].label} · {fmtRelative(a.updatedAt)}
                          </span>
                        </div>
                        <Link to={`/alerts?focus=${encodeURIComponent(a.id)}`} className="todo-title">
                          {a.title.replace(/^[^:]+:\s*/, '')}
                        </Link>
                        <span className="muted small">{a.description}</span>
                      </div>
                      <div className="todo-actions">
                        {withCases && can('cases:write') && (
                          <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => escalate(a.id)}>
                            Utwórz sprawę
                          </button>
                        )}
                        {a.userKey && supports('endUsers') && (
                          <Link to={`/end-users?focus=${encodeURIComponent(a.userKey)}`} className="btn btn-sm">
                            Użytkownik
                          </Link>
                        )}
                        {can('alerts:write') && a.status === 'new' && (
                          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => acknowledge(a)}>
                            Przyjmij
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )
            }
          </Async>
        </Card>

        <div className="stack">
          {withCases && (
          <Card
            title="Sprawy czekające na decyzję"
            actions={
              <Link to="/cases" className="btn btn-sm btn-ghost">
                Sprawy <Icon name="arrowRight" size={14} />
              </Link>
            }
            padded={false}
          >
            <Async state={cases}>
              {() =>
                waitingCases.length === 0 ? (
                  <p className="card-body muted">Żadna sprawa nie czeka.</p>
                ) : (
                  <ul className="list">
                    {waitingCases.slice(0, 5).map((c) => (
                      <li key={c.id}>
                        <Link to={`/cases/${c.id}`} className="list-link">
                          <Badge tone={SEVERITY[c.priority].tone}>{SEVERITY[c.priority].label}</Badge>
                          <span className="list-main">
                            <span className="list-title">{c.title}</span>
                            <span className="muted small">
                              {caseNeed(c)}
                              {c.forwarding.recommended && !c.forwarding.forwardedTo && c.forwarding.recommendedRole
                                ? ` → ${ROLE_LABEL[c.forwarding.recommendedRole].toLowerCase()}`
                                : ''}{' '}
                              · {c.queryCount} zapytań
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )
              }
            </Async>
          </Card>
          )}

          <Card
            title={lifecycle ? 'Luki informacyjne do podjęcia' : 'Luki informacyjne bez sprawy'}
            subtitle="Ludzie pytają, a brakuje źródeł."
            padded={false}
          >
            <Async state={gaps}>
              {() =>
                gapsWithoutCase.length === 0 ? (
                  <p className="card-body muted">{lifecycle ? 'Żadna luka nie czeka na decyzję.' : 'Każda luka ma już sprawę.'}</p>
                ) : (
                  <ul className="list">
                    {gapsWithoutCase.slice(0, 5).map((g: QueryCluster) => (
                      <li key={g.id}>
                        <Link to={lifecycle ? `/gaps?focus=${encodeURIComponent(g.id)}` : '/gaps'} className="list-link">
                          <span className="gap-count">{lifecycle ? g.uniqueSessions : g.noEvidence}</span>
                          <span className="list-main">
                            <span className="list-title">{g.label}</span>
                            <span className="muted small">
                              {lifecycle
                                ? `${g.uniqueSessions} ${plural(g.uniqueSessions, ['osoba pytała', 'osoby pytały', 'osób pytało'])} · ${fmtPct(g.noEvidenceRatio)} bez dowodów`
                                : `${fmtPct(g.noEvidenceRatio)} bez dowodów`}
                              {g.riskTopics.length ? ` · ${g.riskTopics[0]}` : ''}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )
              }
            </Async>
          </Card>
        </div>
      </div>

      <div className="grid-2">
        <Card title="Stan systemu">
          <ul className="health-list">
            {modelProblems.map(({ a, p }) => (
              <li key={a.role}>
                <StatusDot tone={HEALTH[p.health].tone} />
                <span>
                  <strong>{PIPELINE_ROLE[a.role].label}:</strong> {p.name} — {HEALTH[p.health].label.toLowerCase()}
                  {p.errorRate ? ` (${fmtPct(p.errorRate, 1)} błędów)` : ''}
                </span>
                <Link to="/models" className="small">
                  Zmień model
                </Link>
              </li>
            ))}
            {sourceProblems.map((s) => (
              <li key={s.id}>
                <StatusDot tone="warning" />
                <span>
                  <strong>Źródło:</strong> {s.name} — nieudane pobieranie
                </span>
                <Link to="/sources" className="small">
                  Sprawdź
                </Link>
              </li>
            ))}
            {!!stats.data?.technicalErrors && (
              <li>
                <StatusDot tone="warning" />
                <span>
                  <strong>{stats.data.technicalErrors}</strong> {plural(stats.data.technicalErrors, ['sprawdzenie zakończone', 'sprawdzenia zakończone', 'sprawdzeń zakończonych'])} błędem technicznym (24 h)
                </span>
                <Link to="/checks" className="small">
                  Zobacz
                </Link>
              </li>
            )}
            {!!stats.data?.pending && (
              <li>
                <StatusDot tone="muted" />
                <span>
                  <strong>{stats.data.pending}</strong> {plural(stats.data.pending, ['zapytanie bez zapisanego wyniku', 'zapytania bez zapisanego wyniku', 'zapytań bez zapisanego wyniku'])} (w toku lub przerwane)
                </span>
              </li>
            )}
            {systemIssues === 0 && (
              <li>
                <StatusDot tone="good" />
                <span>
                  {supports('providers') ? 'Wszystkie modele i źródła działają poprawnie.' : 'Brak błędów technicznych w ostatnich 24 godzinach.'}
                </span>
              </li>
            )}
            {supports('runtimeConfig') && can('models:read') && (
              <li>
                <StatusDot tone="muted" />
                <span>Model językowy, źródła danych i klucze API</span>
                <Link to="/runtime" className="small">
                  Konfiguracja
                </Link>
              </li>
            )}
          </ul>
        </Card>

        <Card
          title="Ostatnie 24 godziny"
          actions={
            <Link to="/stats" className="btn btn-sm btn-ghost">
              Więcej <Icon name="arrowRight" size={14} />
            </Link>
          }
        >
          <Async state={stats}>
            {(s) => (
              <div className="mini-stats">
                <div>
                  <span className="mini-value">{fmtInt(s.checks)}</span>
                  <span className="muted small">sprawdzeń</span>
                </div>
                <div>
                  <span className="mini-value">{fmtPct(s.checks ? s.abstained / s.checks : 0)}</span>
                  <span className="muted small">bez dowodów</span>
                </div>
                <div>
                  <span className="mini-value">{fmtDuration(s.medianLatencyMs)}</span>
                  <span className="muted small">typowa odpowiedź</span>
                </div>
                {s.refused === undefined ? (
                  <div>
                    <span className="mini-value">{s.injectionsBlocked}</span>
                    <span className="muted small">odpartych ataków</span>
                  </div>
                ) : (
                  <div>
                    <span className="mini-value">{s.refused}</span>
                    <span className="muted small">odrzuconych</span>
                  </div>
                )}
                {s.users !== undefined && (
                  <div>
                    <span className="mini-value">{fmtInt(s.users)}</span>
                    <span className="muted small">{plural(s.users, ['osoba', 'osoby', 'osób'])}</span>
                  </div>
                )}
                {s.dangerousQueries !== undefined && (
                  <div>
                    <span className="mini-value">{s.dangerousQueries}</span>
                    <span className="muted small">o treści niebezpieczne</span>
                  </div>
                )}
              </div>
            )}
          </Async>
        </Card>
      </div>
    </>
  );
}

function StatusDot({ tone }: { tone: Tone }) {
  return <span className={`status-dot dot-${tone}`} aria-hidden="true" />;
}

function AttentionTile({
  to,
  icon,
  tone,
  count,
  label,
  ok,
}: {
  to: string;
  icon: IconName;
  tone: Tone;
  count: number;
  label: string;
  ok: string;
}) {
  const active = count > 0;
  return (
    <Link to={to} className={`att-tile ${active ? `att-${tone}` : 'att-ok'}`}>
      <span className="att-icon">
        <Icon name={active ? icon : 'check'} size={20} />
      </span>
      <span className="att-text">
        {active ? (
          <>
            <span className="att-count">{count}</span>
            <span className="att-label">{label}</span>
          </>
        ) : (
          <span className="att-label">{ok}</span>
        )}
      </span>
    </Link>
  );
}
