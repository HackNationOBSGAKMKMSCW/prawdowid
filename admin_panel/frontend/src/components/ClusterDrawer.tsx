import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { QueryCluster, Verdict } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime, fmtPct } from '../utils/format.ts';
import { StackedBar, TimeSeriesChart } from './charts.tsx';
import { Icon } from './icons.tsx';
import { ALERT_TYPE, channelLabel, SEVERITY, VERDICT } from './labels.ts';
import { useRefreshCounts } from './Layout.tsx';
import { Badge, Drawer, useAction } from './ui.tsx';

const VERDICTS: Verdict[] = ['confirmed', 'false', 'misleading', 'insufficient', 'not_verifiable'];
const PRIORITY = ['information_gap', 'high_risk', 'query_surge'];

export function ClusterDrawer({ cluster, onClose }: { cluster: QueryCluster | null; onClose: () => void }) {
  const api = getApi();
  const { can } = useAuth();
  const navigate = useNavigate();
  const refreshCounts = useRefreshCounts();
  const { run, busy } = useAction();
  const [openedAt] = useState(() => Date.now());
  const alerts = useAsync(
    () => (cluster ? api.listAlerts({ status: 'any' }).then((l) => l.filter((a) => a.clusterId === cluster.id)) : Promise.resolve([])),
    [cluster?.id],
  );

  if (!cluster) return null;
  const escalationTarget = [...(alerts.data ?? [])]
    .filter((a) => !['resolved', 'dismissed'].includes(a.status))
    .sort((a, b) => PRIORITY.indexOf(a.type) - PRIORITY.indexOf(b.type))[0];

  const createCase = async () => {
    if (!escalationTarget) return;
    let id = '';
    const ok = await run(async () => {
      id = (await api.escalateAlert(escalationTarget.id)).id;
    }, 'Sprawa moderatora utworzona lub zaktualizowana.');
    if (ok) {
      refreshCounts();
      navigate(`/cases/${id}`);
    }
  };

  const hours = cluster.hourly.map((_, i) => {
    const d = new Date(openedAt - (cluster.hourly.length - 1 - i) * 3_600_000);
    return `${String(d.getHours()).padStart(2, '0')}:00`;
  });

  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title="Grupa podobnych zapytań"
      footer={
        <>
          <Link to={`/checks?cluster=${encodeURIComponent(cluster.id)}`} className="btn">
            <Icon name="history" size={16} /> Pokaż zapytania ({cluster.total})
          </Link>
          {cluster.caseId ? (
            <Link to={`/cases/${cluster.caseId}`} className="btn btn-primary">
              <Icon name="folder" size={16} /> Sprawa {cluster.caseId}
            </Link>
          ) : (
            can('cases:write') &&
            escalationTarget && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={createCase}>
                <Icon name="folder" size={16} /> Utwórz sprawę moderatora
              </button>
            )
          )}
        </>
      }
    >
      <h3 className="drawer-title">{cluster.label}</h3>
      <div className="row gap-sm wrap">
        {cluster.isInformationGap && <Badge tone="serious">Luka informacyjna</Badge>}
        {cluster.isSurging && <Badge tone="warning">Szybki wzrost</Badge>}
        {cluster.riskTopics.map((r) => (
          <Badge key={r} tone="critical">
            <Icon name="alert" size={12} /> {r}
          </Badge>
        ))}
        {cluster.keywords.map((k) => (
          <Badge key={k} tone="muted">
            {k}
          </Badge>
        ))}
      </div>

      <dl className="metrics metrics-lg">
        <div>
          <dt>Wszystkie zapytania</dt>
          <dd>{cluster.total}</dd>
        </div>
        <div>
          <dt>W bieżącym oknie</dt>
          <dd>{cluster.inWindow}</dd>
        </div>
        <div>
          <dt>Poprzednie okno</dt>
          <dd>{cluster.previousWindow}</dd>
        </div>
        <div>
          <dt>Bez dowodów</dt>
          <dd>
            {cluster.noEvidence} ({fmtPct(cluster.noEvidenceRatio)})
          </dd>
        </div>
        <div>
          <dt>Unikalne sesje (szac.)</dt>
          <dd>{cluster.uniqueSessions}</dd>
        </div>
        <div>
          <dt>Kanały</dt>
          <dd>
            {Object.entries(cluster.channels)
              .map(([k, v]) => `${channelLabel(k)} ${v}`)
              .join(' · ')}
          </dd>
        </div>
      </dl>

      {cluster.missing && (
        <div className="notice notice-warning">
          <Icon name="gap" size={16} />
          <div>
            <strong>Czego nie udało się ustalić:</strong> {cluster.missing}
          </div>
        </div>
      )}

      <h4 className="subhead">Zapytania w ostatnich 48 h</h4>
      <TimeSeriesChart
        height={170}
        ariaLabel="Zapytania na godzinę w ostatnich 48 godzinach"
        labels={hours}
        series={[{ key: 'q', label: 'Zapytania na godzinę', color: 'var(--series-1)', values: cluster.hourly, area: true }]}
      />

      <h4 className="subhead">Wyniki w tej grupie</h4>
      <StackedBar
        ariaLabel="Wyniki w grupie"
        segments={VERDICTS.map((v) => ({ key: v, label: VERDICT[v].label, value: cluster.verdicts[v] ?? 0, tone: VERDICT[v].tone }))}
      />

      <h4 className="subhead">Przykładowe zapytania (dane osobowe zamaskowane)</h4>
      <ul className="quotes">
        {cluster.sampleQueries.map((q) => (
          <li key={q}>{q}</li>
        ))}
      </ul>

      <h4 className="subhead">Powiązane alerty</h4>
      {(alerts.data ?? []).length === 0 ? (
        <p className="muted small">Brak alertów dla tej grupy.</p>
      ) : (
        <ul className="list compact">
          {(alerts.data ?? []).map((a) => (
            <li key={a.id}>
              <Link to={`/alerts?focus=${encodeURIComponent(a.id)}`} className="list-link">
                <Badge tone={SEVERITY[a.severity].tone}>{SEVERITY[a.severity].label}</Badge>
                <span className="list-main">
                  <span className="list-title">{ALERT_TYPE[a.type].label}</span>
                  <span className="muted small">{a.rule}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        Pierwsze zapytanie: {fmtDateTime(cluster.firstSeen)} · ostatnie: {fmtDateTime(cluster.lastSeen)}
      </p>
    </Drawer>
  );
}
