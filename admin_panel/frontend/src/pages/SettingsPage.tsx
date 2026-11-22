import { useState } from 'react';
import { getApi } from '../api/index.ts';
import { MockAdminApi } from '../api/mock/MockAdminApi.ts';
import type { PrivacySettings } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { getConfig } from '../config.ts';
import { Icon } from '../components/icons.tsx';
import { HEALTH } from '../components/labels.ts';
import { Async, Badge, Card, Field, Modal, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime, fmtDuration } from '../utils/format.ts';

export default function SettingsPage() {
  const api = getApi();
  const config = getConfig();
  const { can, logout } = useAuth();
  const channels = useAsync(() => api.listChannels(), []);
  const privacyRemote = useAsync(() => api.getPrivacy(), []);
  const [draft, setPrivacy] = useState<PrivacySettings | null>(null);
  const privacy = draft ?? privacyRemote.data ?? null;
  const [health, setHealth] = useState<string | null>(null);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const { run, busy } = useAction();
  const editable = can('settings:write');

  const dirty = !!draft && !!privacyRemote.data && JSON.stringify(draft) !== JSON.stringify(privacyRemote.data);

  return (
    <>
      <PageHeader
        title="Kanały i prywatność"
        description="Kanały komunikacji korzystają z tej samej logiki weryfikacji. Tu ustawiasz też retencję i maskowanie danych osobowych."
      />

      <Card title="Kanały komunikacji" subtitle="Ten sam wynik merytoryczny niezależnie od kanału — sprawdzane testem spójności." padded={false}>
        <Async state={channels}>
          {(list) => (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Kanał</th>
                    <th>Stan</th>
                    <th className="num">Zapytania 24 h</th>
                    <th className="num">Mediana czasu</th>
                    <th>Test spójności</th>
                    <th>Włączony</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((ch) => (
                    <tr key={ch.id}>
                      <td>
                        <strong>{ch.name}</strong>
                        {ch.demoAdapter && (
                          <div>
                            <Badge tone="info">adapter demonstracyjny</Badge>
                          </div>
                        )}
                        {ch.operatorCostNote && <div className="muted small">{ch.operatorCostNote}</div>}
                      </td>
                      <td>
                        <Badge tone={HEALTH[ch.health].tone}>{HEALTH[ch.health].label}</Badge>
                      </td>
                      <td className="num">{ch.requests24h}</td>
                      <td className="num">{fmtDuration(ch.medianLatencyMs)}</td>
                      <td className="small">
                        {ch.consistency.total > 0 ? (
                          <>
                            <Badge tone={ch.consistency.passed === ch.consistency.total ? 'good' : 'critical'}>
                              {ch.consistency.passed}/{ch.consistency.total}
                            </Badge>
                            <div className="muted">{fmtDateTime(ch.consistency.lastRunAt)}</div>
                          </>
                        ) : (
                          <span className="muted">nie uruchamiano</span>
                        )}
                      </td>
                      <td>
                        <Toggle
                          checked={ch.enabled}
                          disabled={!can('channels:write') || busy}
                          label={ch.enabled ? 'Tak' : 'Nie'}
                          onChange={(enabled) =>
                            run(async () => {
                              const updated = await api.updateChannel(ch.id, { enabled });
                              channels.setData((l) => (l ?? []).map((c) => (c.id === updated.id ? { ...c, enabled: updated.enabled } : c)));
                            }, enabled ? 'Kanał włączony.' : 'Kanał wyłączony.')
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Card>

      <div className="grid-2">
        <Card
          title="Prywatność i retencja"
          subtitle="Minimalizacja danych: przechowujemy tylko to, co potrzebne do zapisu przebiegu sprawdzenia."
          actions={
            editable && (
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={!dirty || busy}
                onClick={() =>
                  privacy &&
                  run(async () => {
                    privacyRemote.setData(await api.updatePrivacy(privacy));
                    setPrivacy(null);
                  }, 'Ustawienia prywatności zapisane.')
                }
              >
                Zapisz
              </button>
            )
          }
        >
          <Async state={privacyRemote}>
            {() =>
              privacy && (
                <fieldset disabled={!editable} className="plain-fieldset form-grid">
                  <Toggle
                    checked={privacy.maskPii}
                    onChange={(v) => setPrivacy({ ...privacy, maskPii: v })}
                    label="Automatyczne maskowanie danych osobowych"
                    description="Imiona i nazwiska, numery telefonów, e-maile, PESEL — zastępowane znacznikami przed zapisem i wysłaniem do modelu."
                  />
                  <Toggle
                    checked={privacy.storeFullContent}
                    onChange={(v) => setPrivacy({ ...privacy, storeFullContent: v })}
                    label="Przechowuj pełną treść pobranych stron i obrazów"
                    description="Domyślnie wyłączone. Włączenie wymaga podstawy prawnej, licencji i procedury usunięcia."
                  />
                  <Toggle
                    checked={privacy.logIpAddresses}
                    onChange={(v) => setPrivacy({ ...privacy, logIpAddresses: v })}
                    label="Zapisuj adresy IP"
                    description="Tylko na potrzeby limitów zapytań; domyślnie wyłączone."
                  />
                  {privacy.storeFullContent && (
                    <div className="notice notice-warning">
                      <Icon name="alert" size={16} /> Archiwizacja pełnych treści wymaga określenia podstawy prawnej, licencji,
                      retencji, kontroli dostępu i procedury usunięcia.
                    </div>
                  )}
                  <div className="form-row">
                    <Field label="Retencja zapisów (dni)">
                      <input type="number" min={1} max={365} value={privacy.retentionDays} onChange={(e) => setPrivacy({ ...privacy, retentionDays: Number(e.target.value) })} />
                    </Field>
                    <Field label="Anonimizacja po (dniach)">
                      <input type="number" min={1} max={365} value={privacy.anonymizeAfterDays} onChange={(e) => setPrivacy({ ...privacy, anonymizeAfterDays: Number(e.target.value) })} />
                    </Field>
                  </div>
                </fieldset>
              )
            }
          </Async>
          {editable && (
            <div className="danger-zone">
              <div>
                <strong>Usuń dane sesji demonstracyjnej</strong>
                <div className="muted small">Trwale usuwa historię sprawdzeń z tej sesji. Operacja trafia do dziennika audytu.</div>
              </div>
              <button type="button" className="btn btn-danger btn-sm" onClick={() => setPurgeOpen(true)}>
                <Icon name="trash" size={14} /> Usuń
              </button>
            </div>
          )}
        </Card>

        <Card title="Połączenie z API" subtitle="Adres i ścieżki API pochodzą z konfiguracji — nie są zapisane w kodzie.">
          <dl className="kv">
            <dt>Źródło danych</dt>
            <dd>{config.dataSource === 'mock' ? <Badge tone="warning">mock — dane przykładowe</Badge> : <Badge tone="good">http — API</Badge>}</dd>
            <dt>Adres bazowy</dt>
            <dd>
              <code>{config.apiBaseUrl}</code>
            </dd>
            <dt>Limit czasu żądania</dt>
            <dd>{config.requestTimeoutMs / 1000} s</dd>
            <dt>Środowisko</dt>
            <dd>{config.environmentLabel || '—'}</dd>
            <dt>Plik konfiguracyjny</dt>
            <dd>
              <code>/config.json</code> (zmiana bez przebudowy)
            </dd>
          </dl>
          <div className="row gap-sm wrap">
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const h = await api.health();
                  setHealth(`${h.status}${h.version ? ` · wersja ${h.version}` : ''}`);
                })
              }
            >
              <Icon name="plug" size={14} /> Sprawdź połączenie
            </button>
            {health && <Badge tone="good">{health}</Badge>}
            {api instanceof MockAdminApi && editable && (
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => {
                  (api as MockAdminApi).resetDemo();
                  logout('Dane demonstracyjne przywrócone. Zaloguj się ponownie.');
                  window.location.reload();
                }}
              >
                <Icon name="refresh" size={14} /> Przywróć dane demo
              </button>
            )}
          </div>
          <details className="config-details">
            <summary>Ścieżki endpointów</summary>
            <table className="table table-compact">
              <tbody>
                {Object.entries(config.endpoints).map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono small">{k}</td>
                    <td className="mono small">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </Card>
      </div>

      <Modal
        open={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        title="Usunąć dane sesji demonstracyjnej?"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setPurgeOpen(false)}>
              Anuluj
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={async () => {
                let n = 0;
                const ok = await run(async () => {
                  n = (await api.purgeDemoData()).deletedChecks;
                });
                if (ok) {
                  setPurgeOpen(false);
                  channels.reload();
                  window.alert(`Usunięto ${n} zapisów sprawdzeń.`);
                }
              }}
            >
              Usuń trwale
            </button>
          </>
        }
      >
        <p>Wszystkie zapisy sprawdzeń z sesji demonstracyjnej zostaną usunięte. Tej operacji nie można cofnąć.</p>
      </Modal>
    </>
  );
}
