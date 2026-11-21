import { type FormEvent, useState } from 'react';
import { getApi } from '../api/index.ts';
import type {
  ModelProvider,
  PipelineAssignment,
  PipelineRole,
  ProcessingRegion,
  ProviderInput,
  ProviderProtocol,
  ProviderTestResult,
} from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { HEALTH, PIPELINE_ROLE, PROTOCOL, REGION } from '../components/labels.ts';
import { Async, Badge, Card, Field, Modal, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime, fmtDuration, fmtPct, fmtRelative } from '../utils/format.ts';

const LLM_ROLES: PipelineRole[] = ['claim_extraction', 'answer_generation'];

const EMPTY_PROVIDER: ProviderInput = {
  name: '',
  vendor: '',
  protocol: 'openai_compatible',
  model: '',
  baseUrl: 'https://',
  region: 'EOG',
  roles: ['claim_extraction'],
  keyRef: '',
  costPer1kInputPln: 0,
  costPer1kOutputPln: 0,
  notes: '',
};

export default function ModelsPage() {
  const api = getApi();
  const { can } = useAuth();
  const providers = useAsync(() => api.listProviders(), []);
  const assignments = useAsync(() => api.listAssignments(), []);
  const { run, busy } = useAction();
  const [editing, setEditing] = useState<PipelineAssignment | null>(null);
  const [draft, setDraft] = useState<{ providerId: string; fallback: string[]; timeoutS: number; maxRetries: number; temperature?: number }>({
    providerId: '',
    fallback: [],
    timeoutS: 30,
    maxRetries: 2,
  });
  const [tests, setTests] = useState<Record<string, ProviderTestResult & { at: number }>>({});
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<ProviderInput>(EMPTY_PROVIDER);
  const writable = can('models:write');

  const byId = new Map((providers.data ?? []).map((p) => [p.id, p]));

  const openEdit = (a: PipelineAssignment) => {
    setDraft({
      providerId: a.providerId ?? '',
      fallback: a.fallbackProviderIds,
      timeoutS: a.params.timeoutS,
      maxRetries: a.params.maxRetries,
      temperature: a.params.temperature,
    });
    setEditing(a);
  };

  const saveAssignment = async () => {
    if (!editing) return;
    let updated: PipelineAssignment | null = null;
    const ok = await run(async () => {
      updated = await api.updateAssignment(editing.role, {
        providerId: draft.providerId || null,
        fallbackProviderIds: draft.fallback,
        params: { timeoutS: draft.timeoutS, maxRetries: draft.maxRetries, temperature: draft.temperature },
      });
    }, 'Zapisano. Nowe zapytania używają wybranego modelu.');
    if (ok && updated) {
      const next = updated as PipelineAssignment;
      assignments.setData((list) => (list ?? []).map((a) => (a.role === next.role ? next : a)));
      setEditing(null);
    }
  };

  const test = async (p: ModelProvider) => {
    await run(async () => {
      const result = await api.testProvider(p.id);
      setTests((t) => ({ ...t, [p.id]: { ...result, at: Date.now() } }));
    });
  };

  const addProvider = async (e: FormEvent) => {
    e.preventDefault();
    let created: ModelProvider | null = null;
    const ok = await run(async () => {
      created = await api.createProvider({ ...form, keyRef: form.keyRef?.trim() || undefined });
    }, 'Dostawca dodany. Ustaw klucz w magazynie sekretów serwera, a potem przetestuj połączenie.');
    if (ok && created) {
      providers.setData((list) => [...(list ?? []), created as ModelProvider]);
      setAdding(false);
      setForm(EMPTY_PROVIDER);
    }
  };

  const remove = async (p: ModelProvider) => {
    const ok = await run(() => api.deleteProvider(p.id), 'Dostawca usunięty.');
    if (ok) providers.setData((list) => (list ?? []).filter((x) => x.id !== p.id));
  };

  const candidates = editing ? (providers.data ?? []).filter((p) => p.roles.includes(editing.role)) : [];
  const chosen = byId.get(draft.providerId);

  return (
    <>
      <PageHeader
        title="Modele i dostawcy"
        description="Każdy etap weryfikacji korzysta z wymiennego modelu. Zmiana dostawcy to jedna decyzja w panelu — bez przebudowy systemu. Klucze API są przechowywane wyłącznie po stronie serwera; panel widzi tylko, czy są skonfigurowane."
        actions={
          writable && (
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setAdding(true)}>
              <Icon name="plus" size={16} /> Dodaj dostawcę
            </button>
          )
        }
      />

      <Async state={assignments}>
        {(list) => (
          <>
            <ProcessingSummary assignments={list} byId={byId} />
            <div className="pipeline-grid">
              {list.map((a) => {
                const p = a.providerId ? byId.get(a.providerId) : undefined;
                return (
                  <Card key={a.role} className={`pipeline-card ${a.enabled ? '' : 'is-off'}`}>
                    <div className="pipeline-head">
                      <div>
                        <h3>{PIPELINE_ROLE[a.role].label}</h3>
                        <p className="muted small">{PIPELINE_ROLE[a.role].description}</p>
                      </div>
                      {writable ? (
                        <Toggle
                          checked={a.enabled}
                          label={a.enabled ? 'Włączony' : 'Wyłączony'}
                          disabled={busy || (!a.providerId && !a.enabled)}
                          onChange={(enabled) =>
                            run(async () => {
                              const updated = await api.updateAssignment(a.role, { enabled });
                              assignments.setData((l) => (l ?? []).map((x) => (x.role === updated.role ? updated : x)));
                            }, enabled ? 'Etap włączony.' : 'Etap wyłączony — funkcja zostanie ujawniona jako niedostępna.')
                          }
                        />
                      ) : (
                        <Badge tone={a.enabled ? 'good' : 'muted'}>{a.enabled ? 'Włączony' : 'Wyłączony'}</Badge>
                      )}
                    </div>
                    {p ? (
                      <div className="pipeline-model">
                        <div className="row gap-sm wrap">
                          <strong>{p.name}</strong>
                          <Badge tone={REGION[p.region].tone}>{REGION[p.region].label}</Badge>
                          <Badge tone={HEALTH[p.health].tone}>{HEALTH[p.health].label}</Badge>
                        </div>
                        <code className="model-id">{p.model}</code>
                        <dl className="metrics">
                          <div>
                            <dt>Mediana opóźnienia</dt>
                            <dd>{p.latencyP50Ms ? fmtDuration(p.latencyP50Ms) : '—'}</dd>
                          </div>
                          <div>
                            <dt>Błędy</dt>
                            <dd>{p.errorRate !== undefined ? fmtPct(p.errorRate, 1) : '—'}</dd>
                          </div>
                          <div>
                            <dt>Koszt / 1k tok.</dt>
                            <dd>{(p.costPer1kInputPln + p.costPer1kOutputPln).toFixed(4).replace('.', ',')} zł</dd>
                          </div>
                        </dl>
                      </div>
                    ) : (
                      <p className="muted">Brak przypisanego modelu — etap niedostępny (system ujawnia to użytkownikowi).</p>
                    )}
                    <div className="small">
                      <span className="muted">Zapasowe: </span>
                      {a.fallbackProviderIds.length
                        ? a.fallbackProviderIds.map((id) => byId.get(id)?.model ?? id).join(' → ')
                        : 'brak'}
                    </div>
                    <div className="muted small">
                      Limit {a.params.timeoutS} s · ponowienia {a.params.maxRetries}
                      {a.params.temperature !== undefined && ` · temperatura ${a.params.temperature}`}
                    </div>
                    <div className="pipeline-foot">
                      <span className="muted small" title={fmtDateTime(a.updatedAt)}>
                        zmiana {fmtRelative(a.updatedAt)} · {a.updatedBy}
                      </span>
                      {writable && (
                        <button type="button" className="btn btn-sm" onClick={() => openEdit(a)}>
                          <Icon name="refresh" size={14} /> Zmień model
                        </button>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          </>
        )}
      </Async>

      <Card title="Rejestr dostawców" subtitle="Lista modeli, które można podłączyć do etapów potoku." padded={false}>
        <Async state={providers}>
          {(list) => (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Dostawca</th>
                    <th>Model</th>
                    <th>Przetwarzanie</th>
                    <th>Klucz API</th>
                    <th>Stan</th>
                    <th>Akcje</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => {
                    const used = (assignments.data ?? []).filter((a) => a.providerId === p.id || a.fallbackProviderIds.includes(p.id));
                    const t = tests[p.id];
                    return (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                          <div className="muted small">{p.vendor}</div>
                          <div className="row gap-xs wrap">
                            {p.roles.map((r) => (
                              <Badge key={r} tone="muted">
                                {PIPELINE_ROLE[r].label}
                              </Badge>
                            ))}
                          </div>
                          {p.notes && <div className="muted small note-line">{p.notes}</div>}
                        </td>
                        <td>
                          <code className="small">{p.model}</code>
                          <div className="muted small">{PROTOCOL[p.protocol]}</div>
                          <div className="muted small mono break">{p.baseUrl}</div>
                        </td>
                        <td>
                          <Badge tone={REGION[p.region].tone}>{REGION[p.region].label}</Badge>
                        </td>
                        <td className="small">
                          {p.keyConfigured ? (
                            <Badge tone="good">
                              <Icon name="check" size={12} /> {p.keyRef ? 'Skonfigurowany' : 'Niewymagany'}
                            </Badge>
                          ) : (
                            <Badge tone="warning">Brak</Badge>
                          )}
                          {p.keyRef && <div className="muted mono">{p.keyRef}</div>}
                        </td>
                        <td className="small">
                          <Badge tone={HEALTH[p.health].tone}>{HEALTH[p.health].label}</Badge>
                          {t && (
                            <div className={t.ok ? 'text-good' : 'text-critical'}>
                              {t.ok ? `Test OK · ${fmtDuration(t.latencyMs)}` : 'Test nieudany'} — {t.message}
                            </div>
                          )}
                          {used.length > 0 && <div className="muted">używany w {used.length} etap(ach)</div>}
                        </td>
                        <td>
                          <div className="row gap-xs wrap">
                            <button type="button" className="btn btn-xs" disabled={busy} onClick={() => test(p)}>
                              <Icon name="plug" size={12} /> Test
                            </button>
                            {writable && used.length === 0 && (
                              <button type="button" className="btn btn-xs btn-ghost" disabled={busy} onClick={() => remove(p)}>
                                <Icon name="trash" size={12} /> Usuń
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Card>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing ? `Zmień model: ${PIPELINE_ROLE[editing.role].label}` : ''}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setEditing(null)}>
              Anuluj
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={saveAssignment}>
              Zapisz i przełącz
            </button>
          </>
        }
      >
        {editing && (
          <div className="form-grid">
            <Field label="Model główny">
              <select value={draft.providerId} onChange={(e) => setDraft({ ...draft, providerId: e.target.value, fallback: draft.fallback.filter((f) => f !== e.target.value) })}>
                <option value="">— brak (etap niedostępny) —</option>
                {candidates.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.keyConfigured}>
                    {p.name} · {p.model} · {REGION[p.region].label}
                    {!p.keyConfigured ? ' — brak klucza' : ''}
                  </option>
                ))}
              </select>
            </Field>
            {chosen?.region === 'poza_EOG' && (
              <div className="notice notice-warning">
                <Icon name="alert" size={16} />
                <div>
                  Ten dostawca przetwarza dane <strong>poza EOG</strong>. Treść zapytań (po maskowaniu danych osobowych)
                  opuści EOG — upewnij się, że jest na to podstawa prawna, i odnotuj to w dokumentacji.
                </div>
              </div>
            )}
            <fieldset className="fieldset">
              <legend className="field-label">Modele zapasowe (kolejność = priorytet)</legend>
              {candidates
                .filter((p) => p.id !== draft.providerId)
                .map((p) => (
                  <label key={p.id} className="check-row">
                    <input
                      type="checkbox"
                      disabled={!p.keyConfigured}
                      checked={draft.fallback.includes(p.id)}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          fallback: e.target.checked ? [...draft.fallback, p.id] : draft.fallback.filter((f) => f !== p.id),
                        })
                      }
                    />
                    <span>
                      {p.name} <span className="muted small">({REGION[p.region].label}{!p.keyConfigured ? ', brak klucza' : ''})</span>
                    </span>
                  </label>
                ))}
              {candidates.length <= 1 && <p className="muted small">Brak innych dostawców obsługujących ten etap.</p>}
            </fieldset>
            <div className="form-row">
              <Field label="Limit czasu (s)">
                <input type="number" min={1} max={120} value={draft.timeoutS} onChange={(e) => setDraft({ ...draft, timeoutS: Number(e.target.value) })} />
              </Field>
              <Field label="Ponowienia">
                <input type="number" min={0} max={5} value={draft.maxRetries} onChange={(e) => setDraft({ ...draft, maxRetries: Number(e.target.value) })} />
              </Field>
              {LLM_ROLES.includes(editing.role) && (
                <Field label="Temperatura">
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.1}
                    value={draft.temperature ?? 0}
                    onChange={(e) => setDraft({ ...draft, temperature: Number(e.target.value) })}
                  />
                </Field>
              )}
            </div>
            <p className="muted small">
              Zmiana obowiązuje dla nowych zapytań i jest zapisywana w dzienniku audytu. Po zmianie modelu uruchom zestaw
              testów referencyjnych, aby porównać jakość (macro-F1, poprawność cytowań).
            </p>
          </div>
        )}
      </Modal>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="Dodaj dostawcę modelu"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              Anuluj
            </button>
            <button type="submit" form="provider-form" className="btn btn-primary" disabled={busy}>
              Dodaj
            </button>
          </>
        }
      >
        <form id="provider-form" className="form-grid" onSubmit={addProvider}>
          <div className="form-row">
            <Field label="Nazwa wyświetlana">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={80} />
            </Field>
            <Field label="Dostawca">
              <input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} maxLength={80} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Protokół">
              <select value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value as ProviderProtocol })}>
                {Object.entries(PROTOCOL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Identyfikator modelu">
              <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} required placeholder="np. mistral-small-latest" maxLength={120} />
            </Field>
          </div>
          <Field label="Adres bazowy API">
            <input value={form.baseUrl} onChange={(e) => setForm({ ...form, baseUrl: e.target.value })} required maxLength={200} />
          </Field>
          <div className="form-row">
            <Field label="Miejsce przetwarzania danych">
              <select value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value as ProcessingRegion })}>
                {Object.entries(REGION).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Nazwa sekretu z kluczem" hint="Sam klucz dodaje administrator infrastruktury po stronie serwera — nigdy w panelu.">
              <input value={form.keyRef} onChange={(e) => setForm({ ...form, keyRef: e.target.value.toUpperCase() })} placeholder="np. MISTRAL_API_KEY" maxLength={64} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Koszt wejścia (zł / 1k tokenów)">
              <input type="number" min={0} step={0.0001} value={form.costPer1kInputPln} onChange={(e) => setForm({ ...form, costPer1kInputPln: Number(e.target.value) })} />
            </Field>
            <Field label="Koszt wyjścia (zł / 1k tokenów)">
              <input type="number" min={0} step={0.0001} value={form.costPer1kOutputPln} onChange={(e) => setForm({ ...form, costPer1kOutputPln: Number(e.target.value) })} />
            </Field>
          </div>
          <fieldset className="fieldset">
            <legend className="field-label">Zastosowania</legend>
            {(Object.keys(PIPELINE_ROLE) as PipelineRole[]).map((r) => (
              <label key={r} className="check-row">
                <input
                  type="checkbox"
                  checked={form.roles.includes(r)}
                  onChange={(e) => setForm({ ...form, roles: e.target.checked ? [...form.roles, r] : form.roles.filter((x) => x !== r) })}
                />
                <span>{PIPELINE_ROLE[r].label}</span>
              </label>
            ))}
          </fieldset>
          <Field label="Uwagi (opcjonalnie)">
            <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} maxLength={200} />
          </Field>
        </form>
      </Modal>
    </>
  );
}

function ProcessingSummary({ assignments, byId }: { assignments: PipelineAssignment[]; byId: Map<string, ModelProvider> }) {
  const outside = assignments.filter((a) => {
    if (!a.enabled || !a.providerId) return false;
    return byId.get(a.providerId)?.region === 'poza_EOG';
  });
  return outside.length === 0 ? (
    <div className="notice notice-good">
      <Icon name="shield" size={16} />
      <div>
        <strong>Wszystkie aktywne etapy przetwarzają dane w EOG lub na własnej infrastrukturze.</strong> Zapasowe modele
        mogą mieć inny region — sprawdź listę poniżej.
      </div>
    </div>
  ) : (
    <div className="notice notice-warning">
      <Icon name="alert" size={16} />
      <div>
        <strong>Przetwarzanie poza EOG:</strong> {outside.map((a) => PIPELINE_ROLE[a.role].label).join(', ')}.
      </div>
    </div>
  );
}
