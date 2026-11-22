import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { EndUser, EndUserFilter } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { ALERT_STATUS, channelLabel, OUTCOME, SEVERITY, VERDICT } from '../components/labels.ts';
import { useRefreshCounts } from '../components/Layout.tsx';
import { Async, Badge, Card, Drawer, EmptyState, Field, Kpi, Modal, PageHeader, SearchInput, Tabs, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtDateTime, fmtRelative, truncate } from '../utils/format.ts';

const FILTERS: { value: EndUserFilter; label: string }[] = [
  { value: 'all', label: 'Wszyscy' },
  { value: 'flagged', label: 'Treści niebezpieczne' },
  { value: 'blocked', label: 'Zablokowani' },
];

const DURATIONS = [
  { value: '24', label: '24 godziny' },
  { value: '72', label: '3 dni' },
  { value: '168', label: '7 dni' },
  { value: '720', label: '30 dni' },
  { value: 'permanent', label: 'Bezterminowo' },
];

function BlockState({ user }: { user: EndUser }) {
  if (!user.blocked) return <Badge tone="good">Aktywny</Badge>;
  return (
    <Badge tone="critical" title={user.blockReason ?? undefined}>
      <Icon name="lock" size={12} /> {user.permanent ? 'Zablokowany bezterminowo' : `Zablokowany do ${fmtDateTime(user.blockedUntil ?? undefined)}`}
    </Badge>
  );
}

export default function EndUsersPage() {
  const api = getApi();
  const { can } = useAuth();
  const refreshCounts = useRefreshCounts();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<EndUserFilter>('all');
  const [search, setSearch] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? params.get('focus');
  const users = useAsync(() => api.listEndUsers(filter), [filter]);
  const all = useAsync(() => api.listEndUsers('all'), []);

  const close = () => {
    setPicked(null);
    if (params.has('focus')) {
      params.delete('focus');
      setParams(params, { replace: true });
    }
  };

  const reload = () => {
    users.reload();
    all.reload();
    refreshCounts();
  };

  const needle = search.trim().toLowerCase();
  const rows = (users.data ?? []).filter(
    (u) => !needle || u.label.toLowerCase().includes(needle) || u.key.toLowerCase().includes(needle),
  );
  const everyone = all.data ?? [];

  const exportRows = (format: 'csv' | 'json') => {
    if (format === 'json') return exportJson('uzytkownicy-serwisu', rows);
    exportCsv('uzytkownicy-serwisu', rows, [
      { header: 'pseudonim', value: (u) => u.key },
      { header: 'identyfikator (maska)', value: (u) => u.label },
      { header: 'zapytania', value: (u) => u.queries },
      { header: 'treści niebezpieczne', value: (u) => u.dangerous },
      { header: 'pierwsze', value: (u) => u.firstSeen },
      { header: 'ostatnie', value: (u) => u.lastSeen },
      { header: 'zablokowany do', value: (u) => (u.blocked ? (u.blockedUntil ?? '') : '') },
      { header: 'powód blokady', value: (u) => (u.blocked ? (u.blockReason ?? '') : '') },
    ]);
  };

  return (
    <>
      <PageHeader
        title="Użytkownicy serwisu"
        description="Osoby, które piszą do Prawdowida (np. przez WhatsApp). Panel zna tylko pseudonim (HMAC) i zamaskowany numer. Blokada sprawia, że kolejne wiadomości nie są sprawdzane."
        actions={
          can('export') ? (
            <>
              <button type="button" className="btn btn-sm" onClick={() => exportRows('csv')}>
                <Icon name="download" size={16} /> CSV
              </button>
              <button type="button" className="btn btn-sm" onClick={() => exportRows('json')}>
                <Icon name="download" size={16} /> JSON
              </button>
            </>
          ) : undefined
        }
      />

      <div className="kpi-grid kpi-grid-3">
        <Kpi icon="users" label="Użytkownicy" value={all.data ? everyone.length : '…'} hint="w okresie przechowywania danych" />
        <Kpi
          icon="alert"
          label="Pytali o treści niebezpieczne"
          value={all.data ? everyone.filter((u) => u.dangerous > 0).length : '…'}
          tone={everyone.some((u) => u.dangerous > 0) ? 'warning' : undefined}
          hint="terroryzm, broń, materiały wybuchowe…"
        />
        <Kpi
          icon="lock"
          label="Zablokowani teraz"
          value={all.data ? everyone.filter((u) => u.blocked).length : '…'}
          tone={everyone.some((u) => u.blocked) ? 'critical' : undefined}
          hint="ręcznie lub automatycznie"
        />
      </div>

      <div className="toolbar">
        <Tabs label="Filtr użytkowników" value={filter} onChange={setFilter} options={FILTERS} />
        <SearchInput value={search} onChange={setSearch} placeholder="Szukaj pseudonimu lub końcówki numeru…" />
      </div>

      <Card padded={false}>
        <Async state={users}>
          {() =>
            rows.length === 0 ? (
              <EmptyState title="Brak użytkowników dla wybranego filtra" icon="users" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Użytkownik</th>
                      <th className="num">Zapytania</th>
                      <th className="num">Niebezpieczne</th>
                      <th>Ostatnio</th>
                      <th>Pierwszy raz</th>
                      <th>Stan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((u) => (
                      <tr key={u.key} className="clickable" onClick={() => setPicked(u.key)}>
                        <td>
                          <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); setPicked(u.key); }}>
                            {u.label}
                          </button>
                          <div className="mono small muted">{u.key}</div>
                        </td>
                        <td className="num">{u.queries}</td>
                        <td className="num">{u.dangerous > 0 ? <Badge tone="serious">{u.dangerous}</Badge> : <span className="muted">0</span>}</td>
                        <td className="small nowrap" title={fmtDateTime(u.lastSeen)}>
                          {fmtRelative(u.lastSeen)}
                        </td>
                        <td className="small nowrap">{fmtDateTime(u.firstSeen)}</td>
                        <td>
                          <BlockState user={u} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
      </Card>

      {selected && <EndUserDrawer userKey={selected} onClose={close} onChanged={reload} />}
    </>
  );
}

function EndUserDrawer({ userKey, onClose, onChanged }: { userKey: string; onClose: () => void; onChanged: () => void }) {
  const api = getApi();
  const { can } = useAuth();
  const { run, busy } = useAction();
  const detail = useAsync(() => api.getEndUser(userKey), [userKey]);
  const [blocking, setBlocking] = useState(false);
  const [duration, setDuration] = useState('24');
  const [reason, setReason] = useState('');

  const block = async () => {
    const hours = duration === 'permanent' ? null : Number(duration);
    if (await run(() => api.blockEndUser(userKey, hours, reason), 'Użytkownik zablokowany.')) {
      setBlocking(false);
      setReason('');
      detail.reload();
      onChanged();
    }
  };

  const unblock = async () => {
    if (await run(() => api.unblockEndUser(userKey), 'Blokada zdjęta.')) {
      detail.reload();
      onChanged();
    }
  };

  const user = detail.data;
  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title="Użytkownik serwisu"
      footer={
        user &&
        can('endusers:write') && (
          <>
            {user.blocked ? (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={unblock}>
                <Icon name="check" size={16} /> Odblokuj
              </button>
            ) : (
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setBlocking(true)}>
                <Icon name="lock" size={16} /> Zablokuj
              </button>
            )}
            {user.blocked && (
              <button type="button" className="btn" disabled={busy} onClick={() => setBlocking(true)}>
                Zmień blokadę
              </button>
            )}
          </>
        )
      }
    >
      <Async state={detail}>
        {(u) => (
          <div className="stack">
            <div className="row gap-sm wrap">
              <h3 className="drawer-title">{u.label}</h3>
              <BlockState user={u} />
            </div>
            <p className="mono small muted">Pseudonim: {u.key}</p>

            {u.blocked && u.blockReason && (
              <div className="notice notice-critical">
                <Icon name="lock" size={16} />
                <div>
                  <strong>Powód blokady:</strong> {u.blockReason}
                </div>
              </div>
            )}

            <dl className="metrics metrics-lg">
              <div>
                <dt>Zapytania</dt>
                <dd>{u.totalQueries}</dd>
              </div>
              <div>
                <dt>O treści niebezpieczne</dt>
                <dd>{u.dangerous}</dd>
              </div>
              <div>
                <dt>Pierwszy raz</dt>
                <dd>{fmtDateTime(u.firstSeen)}</dd>
              </div>
              <div>
                <dt>Ostatnio</dt>
                <dd>{fmtDateTime(u.lastSeen)}</dd>
              </div>
            </dl>

            <h4 className="subhead">Alerty</h4>
            {u.alerts.length === 0 ? (
              <p className="muted small">Brak alertów dla tego użytkownika.</p>
            ) : (
              <ul className="list compact">
                {u.alerts.map((a) => (
                  <li key={a.id}>
                    <Link to={`/alerts?focus=${encodeURIComponent(a.id)}&status=any`} className="list-link">
                      <Badge tone={SEVERITY[a.severity].tone}>{SEVERITY[a.severity].label}</Badge>
                      <span className="list-main">
                        <span className="list-title">{a.title}</span>
                        <span className="muted small">
                          {ALERT_STATUS[a.status].label} · {fmtRelative(a.updatedAt)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}

            <h4 className="subhead">Ostatnie zapytania</h4>
            {u.recentQueries.length === 0 ? (
              <p className="muted small">Brak zapisanych zapytań (mogły zostać usunięte po okresie retencji).</p>
            ) : (
              <ul className="list compact">
                {u.recentQueries.map((q) => {
                  const result = q.overallVerdict ? VERDICT[q.overallVerdict] : OUTCOME[q.outcome];
                  return (
                    <li key={q.id}>
                      <Link to={`/checks?focus=${encodeURIComponent(q.id)}`} className="list-link">
                        <Badge tone={result.tone}>{result.label}</Badge>
                        <span className="list-main">
                          <span className="list-title">{truncate(q.query, 110)}</span>
                          <span className="muted small">
                            {fmtDateTime(q.createdAt)} · {channelLabel(q.channel)}
                            {q.riskTopics.length ? ` · ${q.riskTopics.join(', ')}` : ''}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </Async>

      <Modal
        open={blocking}
        onClose={() => setBlocking(false)}
        title={user?.blocked ? 'Zmień blokadę' : 'Zablokuj użytkownika'}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setBlocking(false)}>
              Anuluj
            </button>
            <button type="button" className="btn btn-danger" disabled={busy} onClick={block}>
              Zablokuj
            </button>
          </>
        }
      >
        <p className="muted small">
          Zablokowany użytkownik dostaje informację, że jego zapytania są wstrzymane, a wiadomości nie trafiają do
          weryfikacji. Blokadę można zdjąć w każdej chwili.
        </p>
        <Field label="Na jak długo">
          <select value={duration} onChange={(e) => setDuration(e.target.value)}>
            {DURATIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Powód (opcjonalnie)" hint="Widoczny w panelu; użytkownik go nie widzi.">
          <input type="text" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="np. powtarzające się prośby o instrukcje" />
        </Field>
      </Modal>
    </Drawer>
  );
}
