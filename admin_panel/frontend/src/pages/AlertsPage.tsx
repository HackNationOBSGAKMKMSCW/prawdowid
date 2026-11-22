import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { Alert, AlertQuery, AlertStatus, AlertType, Severity, User } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { ALERT_STATUS, ALERT_TYPE, ROLE_LABEL, SEVERITY } from '../components/labels.ts';
import { useRefreshCounts } from '../components/Layout.tsx';
import { Async, Badge, EmptyState, Field, Modal, PageHeader, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtDateTime, fmtRelative } from '../utils/format.ts';

export default function AlertsPage() {
  const api = getApi();
  const { can } = useAuth();
  const navigate = useNavigate();
  const refreshCounts = useRefreshCounts();
  const [params] = useSearchParams();
  const focus = params.get('focus');
  const [query, setQuery] = useState<AlertQuery>({
    status: (params.get('status') as AlertQuery['status']) ?? 'open',
    type: (params.get('type') as AlertType) ?? 'any',
    severity: 'any',
  });
  const alerts = useAsync(() => api.listAlerts(query), [query.status, query.type, query.severity]);
  const users = useAsync<User[]>(() => (can('cases:read') && supports('staffUsers') ? api.listUsers() : Promise.resolve([])), []);
  const withCases = supports('cases');
  const withRecipients = supports('staffUsers');
  const { run, busy } = useAction();
  const [escalating, setEscalating] = useState<Alert | null>(null);
  const [assignee, setAssignee] = useState('');

  useEffect(() => {
    if (!focus || !alerts.data) return;
    document.getElementById(`alert-${focus}`)?.scrollIntoView({ block: 'center' });
  }, [focus, alerts.data]);

  const setStatus = async (alert: Alert, status: AlertStatus, message: string) => {
    const ok = await run(() => api.updateAlert(alert.id, { status }), message);
    if (ok) {
      alerts.reload();
      refreshCounts();
    }
  };

  const escalate = async () => {
    if (!escalating) return;
    let caseId = '';
    const ok = await run(async () => {
      const c = await api.escalateAlert(escalating.id, assignee || undefined);
      caseId = c.id;
    }, 'Sprawa moderatora utworzona lub zaktualizowana.');
    if (ok) {
      setEscalating(null);
      refreshCounts();
      navigate(`/cases/${caseId}`);
    }
  };

  const exportRows = (list: Alert[], format: 'csv' | 'json') => {
    if (format === 'json') return exportJson('alerty', list);
    exportCsv('alerty', list, [
      { header: 'id', value: (a) => a.id },
      { header: 'typ', value: (a) => ALERT_TYPE[a.type].label },
      { header: 'priorytet', value: (a) => SEVERITY[a.severity].label },
      { header: 'status', value: (a) => ALERT_STATUS[a.status].label },
      { header: 'tytuł', value: (a) => a.title },
      { header: 'reguła', value: (a) => a.rule },
      { header: 'utworzono', value: (a) => a.createdAt },
      { header: 'aktualizacja', value: (a) => a.updatedAt },
      { header: 'liczba zapytań', value: (a) => a.checkIds.length },
      { header: 'sprawa', value: (a) => a.caseId ?? '' },
    ]);
  };

  return (
    <>
      <PageHeader
        title="Alerty i ostrzeżenia"
        description={
          withCases
            ? 'Sygnały z reguł: luki informacyjne, dużo zapytań o to samo, tematy wysokiego ryzyka (np. terroryzm), próby manipulacji i problemy techniczne. Alert nie jest werdyktem.'
            : 'Sygnały z reguł backendu: luki informacyjne, możliwe ataki dezinformacyjne i użytkownicy powtarzający pytania o treści niebezpieczne. Alert nie jest werdyktem.'
        }
        actions={
          can('export') && alerts.data ? (
            <>
              <button type="button" className="btn btn-sm" onClick={() => exportRows(alerts.data ?? [], 'csv')}>
                <Icon name="download" size={16} /> CSV
              </button>
              <button type="button" className="btn btn-sm" onClick={() => exportRows(alerts.data ?? [], 'json')}>
                <Icon name="download" size={16} /> JSON
              </button>
            </>
          ) : undefined
        }
      />

      <div className="toolbar">
        <label className="select-label">
          Status
          <select value={query.status} onChange={(e) => setQuery({ ...query, status: e.target.value as AlertQuery['status'] })}>
            <option value="open">Otwarte</option>
            <option value="any">Wszystkie</option>
            {Object.entries(ALERT_STATUS).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label className="select-label">
          Typ
          <select value={query.type} onChange={(e) => setQuery({ ...query, type: e.target.value as AlertType | 'any' })}>
            <option value="any">Wszystkie typy</option>
            {api.capabilities.alertTypes.map((k) => (
              <option key={k} value={k}>
                {ALERT_TYPE[k].label}
              </option>
            ))}
          </select>
        </label>
        <label className="select-label">
          Priorytet
          <select value={query.severity} onChange={(e) => setQuery({ ...query, severity: e.target.value as Severity | 'any' })}>
            <option value="any">Każdy</option>
            {Object.entries(SEVERITY).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <Async state={alerts}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState title="Brak alertów dla wybranych filtrów" icon="bell" />
          ) : (
            <div className="alert-list">
              {list.map((a) => (
                <article
                  key={a.id}
                  id={`alert-${a.id}`}
                  className={`alert-card sev-${a.severity} ${focus === a.id ? 'is-focused' : ''}`}
                >
                  <div className="alert-head">
                    <div className="row gap-sm wrap">
                      <Badge tone={SEVERITY[a.severity].tone}>
                        {a.severity === 'critical' && <Icon name="alert" size={12} />} {SEVERITY[a.severity].label}
                      </Badge>
                      <Badge tone="neutral">{ALERT_TYPE[a.type].label}</Badge>
                      <Badge tone={ALERT_STATUS[a.status].tone}>{ALERT_STATUS[a.status].label}</Badge>
                    </div>
                    <span className="muted small" title={fmtDateTime(a.updatedAt)}>
                      ostatnie zgłoszenie {fmtRelative(a.updatedAt)}
                    </span>
                  </div>
                  <h3 className="alert-title">{a.title}</h3>
                  <p>{a.description}</p>
                  <div className="alert-rule">
                    <Icon name="sliders" size={14} /> <span>Reguła: {a.rule}</span>
                  </div>
                  <dl className="metrics">
                    {Object.entries(a.metrics).map(([k, v]) => (
                      <div key={k}>
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                  </dl>
                  {a.note && (
                    <div className="alert-rule">
                      <Icon name="info" size={14} /> <span>Notatka: {a.note}</span>
                    </div>
                  )}
                  {withRecipients && (
                  <div className="alert-notify">
                    {a.notified.length > 0 ? (
                      <span>
                        <Icon name="send" size={14} /> <strong>Powiadomiono:</strong>{' '}
                        {[...new Map(a.notified.map((n) => [n.user.id, n])).values()]
                          .map((n) => `${n.user.name} (${ROLE_LABEL[n.user.role].toLowerCase()})`)
                          .join(', ')}{' '}
                        <span className="muted">
                          · {[...new Set(a.notified.map((n) => (n.channel === 'panel' ? 'panel' : 'e-mail')))].join(' + ')} ·{' '}
                          {fmtDateTime(a.notified[0].at)}
                        </span>
                      </span>
                    ) : (
                      <span>
                        <Icon name="info" size={14} /> <strong>Rekomendacja:</strong> powiadomić rolę „
                        {ROLE_LABEL[a.recommendedRole ?? 'moderator'].toLowerCase()}” — nikt nie jest przypisany do tego typu
                        alertu, więc <em>nic nie zostało wysłane</em>.{' '}
                        {can('rules:write') && <Link to="/rules">Ustaw odbiorców</Link>}
                      </span>
                    )}
                  </div>
                  )}
                  <div className="alert-actions">
                    {a.clusterId && (
                      <Link to={`/checks?cluster=${encodeURIComponent(a.clusterId)}`} className="btn btn-sm btn-ghost">
                        Zapytania ({a.queryCount ?? a.checkIds.length})
                      </Link>
                    )}
                    {a.clusterId && a.type === 'information_gap' && supports('gapLifecycle') && (
                      <Link to={`/gaps?focus=${encodeURIComponent(a.clusterId)}`} className="btn btn-sm">
                        <Icon name="gap" size={14} /> Luka informacyjna
                      </Link>
                    )}
                    {a.userKey && supports('endUsers') && (
                      <Link to={`/end-users?focus=${encodeURIComponent(a.userKey)}`} className="btn btn-sm">
                        <Icon name="users" size={14} /> Użytkownik
                      </Link>
                    )}
                    {a.caseId ? (
                      <Link to={`/cases/${a.caseId}`} className="btn btn-sm">
                        <Icon name="folder" size={14} /> Sprawa {a.caseId}
                      </Link>
                    ) : (
                      withCases &&
                      can('cases:write') && (
                        <button type="button" className="btn btn-sm btn-primary" onClick={() => { setAssignee(''); setEscalating(a); }}>
                          <Icon name="folder" size={14} /> Utwórz sprawę
                        </button>
                      )
                    )}
                    {can('alerts:write') && a.status === 'new' && (
                      <button type="button" className="btn btn-sm" disabled={busy} onClick={() => setStatus(a, 'acknowledged', 'Alert przyjęty.')}>
                        Przyjmij
                      </button>
                    )}
                    {can('alerts:write') && !['resolved', 'dismissed'].includes(a.status) && (
                      <>
                        <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setStatus(a, 'resolved', 'Alert oznaczony jako rozwiązany.')}>
                          Rozwiązany
                        </button>
                        <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setStatus(a, 'dismissed', 'Alert odrzucony.')}>
                          Odrzuć
                        </button>
                      </>
                    )}
                    {can('alerts:write') && ['resolved', 'dismissed'].includes(a.status) && (
                      <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setStatus(a, 'acknowledged', 'Alert ponownie otwarty.')}>
                        Otwórz ponownie
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )
        }
      </Async>

      <Modal
        open={!!escalating}
        onClose={() => setEscalating(null)}
        title="Utwórz sprawę moderatora"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setEscalating(null)}>
              Anuluj
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={escalate}>
              Utwórz sprawę
            </button>
          </>
        }
      >
        {escalating && (
          <>
            <p>
              <strong>{escalating.title}</strong>
            </p>
            <p className="muted small">
              Jeśli dla tej grupy zapytań istnieje już otwarta sprawa, alert zostanie do niej dołączony — bez
              tworzenia duplikatu. Sprawa dostanie <em>rekomendację</em> przekazania; samo przekazanie wykonujesz
              osobno w widoku sprawy.
            </p>
            <Field label="Osoba prowadząca (opcjonalnie)">
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">— nie przypisuj —</option>
                {(users.data ?? [])
                  .filter((u) => u.active)
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({ROLE_LABEL[u.role].toLowerCase()})
                    </option>
                  ))}
              </select>
            </Field>
          </>
        )}
      </Modal>
    </>
  );
}
