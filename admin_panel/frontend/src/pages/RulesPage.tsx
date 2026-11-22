import { useState } from 'react';
import { getApi } from '../api/index.ts';
import type { AlertRules, AlertType, RiskTopic, Severity, User } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { ALERT_TYPE, ROLE_LABEL, SEVERITY } from '../components/labels.ts';
import { useRefreshCounts } from '../components/Layout.tsx';
import { Async, Card, Field, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';

const NOTIFIABLE: AlertType[] = ['high_risk', 'information_gap', 'query_surge', 'prompt_injection', 'incident_match', 'source_status', 'system'];

export default function RulesPage() {
  const api = getApi();
  const { can } = useAuth();
  const refreshCounts = useRefreshCounts();
  const remote = useAsync(() => api.getAlertRules(), []);
  const users = useAsync<User[]>(() => api.listUsers(), []);
  const [draft, setRules] = useState<AlertRules | null>(null);
  const rules = draft ?? remote.data ?? null;
  const { run, busy } = useAction();
  const editable = can('rules:write');

  const dirty = !!draft && !!remote.data && JSON.stringify(draft) !== JSON.stringify(remote.data);

  const save = async () => {
    if (!rules) return;
    let saved: AlertRules | null = null;
    const ok = await run(async () => {
      saved = await api.updateAlertRules(rules);
    }, 'Reguły zapisane. Alerty są przeliczane według nowych progów.');
    if (ok && saved) {
      remote.setData(saved);
      setRules(null);
      refreshCounts();
    }
  };

  const setTopic = (i: number, patch: Partial<RiskTopic>) => {
    if (!rules) return;
    const topics = rules.highRisk.topics.map((t, idx) => (idx === i ? { ...t, ...patch } : t));
    setRules({ ...rules, highRisk: { ...rules.highRisk, topics } });
  };

  return (
    <>
      <PageHeader
        title="Reguły alertów i powiadomień"
        description="Jawne progi, z których powstają alerty, oraz osoby wskazane do powiadamiania. Bez wskazanego odbiorcy system tylko rekomenduje powiadomienie — niczego nie wysyła."
        actions={
          editable && (
            <>
              <button type="button" className="btn btn-sm" disabled={!dirty || busy} onClick={() => setRules(null)}>
                Cofnij zmiany
              </button>
              <button type="button" className="btn btn-sm btn-primary" disabled={!dirty || busy} onClick={save}>
                Zapisz reguły
              </button>
            </>
          )
        }
      />
      {!editable && (
        <div className="notice notice-info">
          <Icon name="lock" size={16} /> Podgląd — zmiany reguł może wprowadzać administrator.
        </div>
      )}
      <Async state={remote}>
        {() =>
          rules && (
            <fieldset disabled={!editable} className="plain-fieldset">
              <div className="grid-2">
                <Card title="Luka informacyjna" subtitle="Wiele podobnych zapytań, na które system nie znalazł dowodów.">
                  <Toggle checked={rules.informationGap.enabled} onChange={(v) => setRules({ ...rules, informationGap: { ...rules.informationGap, enabled: v } })} label="Reguła aktywna" />
                  <div className="form-row">
                    <Field label="Min. liczba zapytań">
                      <input type="number" min={1} value={rules.informationGap.minQueries} onChange={(e) => setRules({ ...rules, informationGap: { ...rules.informationGap, minQueries: Number(e.target.value) } })} />
                    </Field>
                    <Field label="Okno (godziny)">
                      <input type="number" min={1} max={168} value={rules.informationGap.windowHours} onChange={(e) => setRules({ ...rules, informationGap: { ...rules.informationGap, windowHours: Number(e.target.value) } })} />
                    </Field>
                  </div>
                  <div className="form-row">
                    <Field label="Min. odsetek bez dowodów (%)">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={Math.round(rules.informationGap.minNoEvidenceRatio * 100)}
                        onChange={(e) => setRules({ ...rules, informationGap: { ...rules.informationGap, minNoEvidenceRatio: Number(e.target.value) / 100 } })}
                      />
                    </Field>
                    <Field label="Próg podobieństwa zapytań" hint="0–1, podobieństwo semantyczne do grupowania">
                      <input
                        type="number"
                        min={0.5}
                        max={1}
                        step={0.05}
                        value={rules.informationGap.similarityThreshold}
                        onChange={(e) => setRules({ ...rules, informationGap: { ...rules.informationGap, similarityThreshold: Number(e.target.value) } })}
                      />
                    </Field>
                  </div>
                </Card>

                <Card title="Dużo zapytań o to samo" subtitle="Szybki wzrost liczby podobnych pytań.">
                  <Toggle checked={rules.querySurge.enabled} onChange={(v) => setRules({ ...rules, querySurge: { ...rules.querySurge, enabled: v } })} label="Reguła aktywna" />
                  <div className="form-row">
                    <Field label="Min. liczba zapytań">
                      <input type="number" min={1} value={rules.querySurge.minQueries} onChange={(e) => setRules({ ...rules, querySurge: { ...rules.querySurge, minQueries: Number(e.target.value) } })} />
                    </Field>
                    <Field label="Okno (godziny)">
                      <input type="number" min={1} max={168} value={rules.querySurge.windowHours} onChange={(e) => setRules({ ...rules, querySurge: { ...rules.querySurge, windowHours: Number(e.target.value) } })} />
                    </Field>
                  </div>
                  <Field label="Wzrost względem poprzedniego okna (×)">
                    <input type="number" min={1} step={0.5} value={rules.querySurge.growthFactor} onChange={(e) => setRules({ ...rules, querySurge: { ...rules.querySurge, growthFactor: Number(e.target.value) } })} />
                  </Field>
                  <h3 className="subhead">Prompt injection</h3>
                  <Toggle checked={rules.promptInjection.enabled} onChange={(v) => setRules({ ...rules, promptInjection: { ...rules.promptInjection, enabled: v } })} label="Alert o serii prób" />
                  <Field label="Min. prób w ciągu godziny">
                    <input type="number" min={1} value={rules.promptInjection.minEventsPerHour} onChange={(e) => setRules({ ...rules, promptInjection: { ...rules.promptInjection, minEventsPerHour: Number(e.target.value) } })} />
                  </Field>
                </Card>
              </div>

              <Card
                title="Tematy wysokiego ryzyka"
                subtitle="Np. terroryzm. Dopasowanie nie jest werdyktem — powoduje ostrzeżenie i powiadomienie wyznaczonych osób."
                actions={
                  editable && (
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() =>
                        setRules({
                          ...rules,
                          highRisk: { ...rules.highRisk, topics: [...rules.highRisk.topics, { id: `rt-${Date.now().toString(36)}`, label: '', keywords: [], severity: 'high' }] },
                        })
                      }
                    >
                      <Icon name="plus" size={14} /> Dodaj temat
                    </button>
                  )
                }
              >
                <div className="row gap-lg wrap">
                  <Toggle checked={rules.highRisk.enabled} onChange={(v) => setRules({ ...rules, highRisk: { ...rules.highRisk, enabled: v } })} label="Wykrywanie tematów wysokiego ryzyka" />
                  <Toggle
                    checked={rules.highRisk.notifyImmediately}
                    onChange={(v) => setRules({ ...rules, highRisk: { ...rules.highRisk, notifyImmediately: v } })}
                    label="Powiadamiaj od pierwszego zapytania"
                    description="Wyłączone: alert dopiero od 3 zapytań w 24 h."
                  />
                </div>
                <div className="topic-list">
                  {rules.highRisk.topics.map((t, i) => (
                    <div key={t.id} className="topic-row">
                      <Field label="Temat">
                        <input value={t.label} onChange={(e) => setTopic(i, { label: e.target.value })} maxLength={80} />
                      </Field>
                      <Field label="Słowa kluczowe (po przecinku, rdzenie bez polskich znaków też działają)">
                        <input
                          value={t.keywords.join(', ')}
                          onChange={(e) => setTopic(i, { keywords: e.target.value.split(',').map((k) => k.trim()).filter(Boolean) })}
                        />
                      </Field>
                      <Field label="Priorytet">
                        <select value={t.severity} onChange={(e) => setTopic(i, { severity: e.target.value as Severity })}>
                          {Object.entries(SEVERITY).map(([k, v]) => (
                            <option key={k} value={k}>
                              {v.label}
                            </option>
                          ))}
                        </select>
                      </Field>
                      {editable && (
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`Usuń temat ${t.label}`}
                          onClick={() => setRules({ ...rules, highRisk: { ...rules.highRisk, topics: rules.highRisk.topics.filter((_, idx) => idx !== i) } })}
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <p className="muted small">
                  Dopasowanie słów kluczowych to pierwszy filtr. Docelowo backend może łączyć je z klasyfikatorem
                  semantycznym — progi i listy pozostają tu jawne i audytowalne.
                </p>
              </Card>

              <Card title="Odbiorcy powiadomień" subtitle="Kogo system faktycznie powiadamia o danym typie alertu (panel, opcjonalnie e-mail).">
                <Toggle checked={rules.notifyByEmail} onChange={(v) => setRules({ ...rules, notifyByEmail: v })} label="Wysyłaj także e-mail" description="Treść wiadomości nie zawiera danych osobowych z zapytań." />
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Typ alertu</th>
                        <th>Odbiorcy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {NOTIFIABLE.map((type) => {
                        const selected = rules.recipients[type] ?? [];
                        return (
                          <tr key={type}>
                            <td>{ALERT_TYPE[type].label}</td>
                            <td>
                              <div className="row gap-sm wrap">
                                {(users.data ?? [])
                                  .filter((u) => u.active)
                                  .map((u) => (
                                    <label key={u.id} className="chip-check">
                                      <input
                                        type="checkbox"
                                        checked={selected.includes(u.id)}
                                        onChange={(e) =>
                                          setRules({
                                            ...rules,
                                            recipients: {
                                              ...rules.recipients,
                                              [type]: e.target.checked ? [...selected, u.id] : selected.filter((x) => x !== u.id),
                                            },
                                          })
                                        }
                                      />
                                      <span>
                                        {u.name} <span className="muted">({ROLE_LABEL[u.role].toLowerCase()})</span>
                                      </span>
                                    </label>
                                  ))}
                                {selected.length === 0 && <span className="muted small">brak — tylko rekomendacja w panelu</span>}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </fieldset>
          )
        }
      </Async>
    </>
  );
}
