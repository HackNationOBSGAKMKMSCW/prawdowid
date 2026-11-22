import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { SecurityEvent } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { BarList } from '../components/charts.tsx';
import { Icon } from '../components/icons.tsx';
import { channelLabel, SECURITY_ACTION, SECURITY_TYPE } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, Kpi, PageHeader } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv } from '../utils/export.ts';
import { fmtDateTime } from '../utils/format.ts';

export default function SecurityPage() {
  const api = getApi();
  const { can } = useAuth();
  const [type, setType] = useState<SecurityEvent['type'] | 'any'>('any');
  const events = useAsync(() => api.listSecurityEvents(168), []);

  return (
    <>
      <PageHeader
        title="Bezpieczeństwo"
        description="Dziennik zdarzeń: próby prompt injection, zablokowane adresy (SSRF), limity zapytań, odrzucone wejścia i nieudane logowania. Treść zgłoszeń i stron źródłowych jest zawsze traktowana jako dane, nigdy jako polecenia."
        actions={
          can('export') && events.data ? (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                exportCsv('zdarzenia-bezpieczenstwa', events.data ?? [], [
                  { header: 'czas', value: (e) => e.at },
                  { header: 'typ', value: (e) => SECURITY_TYPE[e.type] },
                  { header: 'kanał', value: (e) => e.channel },
                  { header: 'opis', value: (e) => e.detail },
                  { header: 'reakcja', value: (e) => SECURITY_ACTION[e.action] },
                  { header: 'sprawdzenie', value: (e) => e.checkId ?? '' },
                ])
              }
            >
              <Icon name="download" size={16} /> CSV
            </button>
          ) : undefined
        }
      />
      <Async state={events}>
        {(list) => {
          const count = (t: SecurityEvent['type']) => list.filter((e) => e.type === t).length;
          const injections = list.filter((e) => e.type === 'prompt_injection');
          const rows = list.filter((e) => type === 'any' || e.type === type);
          return (
            <>
              <div className="kpi-grid kpi-grid-4">
                <Kpi icon="shield" label="Próby prompt injection (7 dni)" value={injections.length} hint={`odparte: ${injections.filter((e) => e.action === 'instructions_ignored' || e.action === 'blocked').length} z ${injections.length}`} />
                <Kpi icon="lock" label="Zablokowane adresy (SSRF)" value={count('ssrf_blocked')} />
                <Kpi icon="refresh" label="Limity zapytań" value={count('rate_limited')} />
                <Kpi icon="users" label="Nieudane logowania do panelu" value={count('auth_failed')} />
              </div>
              <div className="grid-2-1">
                <Card padded={false} title="Zdarzenia" actions={
                  <label className="select-label">
                    Typ
                    <select value={type} onChange={(e) => setType(e.target.value as SecurityEvent['type'] | 'any')}>
                      <option value="any">Wszystkie</option>
                      {Object.entries(SECURITY_TYPE).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                }>
                  {rows.length === 0 ? (
                    <EmptyState title="Brak zdarzeń" icon="shield" />
                  ) : (
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Czas</th>
                            <th>Typ</th>
                            <th>Kanał</th>
                            <th>Opis</th>
                            <th>Reakcja</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.slice(0, 100).map((e) => (
                            <tr key={e.id}>
                              <td className="small nowrap">{fmtDateTime(e.at)}</td>
                              <td>
                                <Badge tone={e.type === 'prompt_injection' ? 'critical' : e.type === 'auth_failed' ? 'warning' : 'neutral'}>{SECURITY_TYPE[e.type]}</Badge>
                              </td>
                              <td className="small">{channelLabel(e.channel)}</td>
                              <td className="small">
                                {e.detail}
                                {e.checkId && (
                                  <div>
                                    <Link to={`/checks?q=${e.checkId}`} className="mono">
                                      {e.checkId}
                                    </Link>
                                  </div>
                                )}
                              </td>
                              <td className="small">{SECURITY_ACTION[e.action]}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
                <div className="stack">
                  <Card title="Zdarzenia według typu">
                    <BarList
                      items={(Object.keys(SECURITY_TYPE) as SecurityEvent['type'][]).map((t) => ({ key: t, label: SECURITY_TYPE[t], value: count(t) }))}
                    />
                  </Card>
                  <Card title="Zabezpieczenia">
                    <ul className="bullets small">
                      <li>Instrukcje systemowe są oddzielone od treści zgłoszeń i pobranych stron.</li>
                      <li>Polecenia znalezione w materiałach nie zmieniają zasad działania — zdarzenie jest zapisywane.</li>
                      <li>Walidacja wejścia: długość, typ pliku, dozwolone schematy URL.</li>
                      <li>Ochrona przed SSRF: blokada adresów prywatnych, pętli zwrotnej i metadanych chmury.</li>
                      <li>Limity zapytań na kanał i nadawcę.</li>
                      <li>Sekrety (klucze API) wyłącznie po stronie serwera; panel ich nie wyświetla.</li>
                      <li>Logowanie do panelu: limit prób, sesja wygasa automatycznie, dziennik audytu.</li>
                    </ul>
                  </Card>
                </div>
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
