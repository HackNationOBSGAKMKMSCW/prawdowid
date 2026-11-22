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
import { Icon, type IconName } from '../components/icons.tsx';
import { HEALTH, PIPELINE_ROLE, PROTOCOL, REGION } from '../components/labels.ts';
import { Async, Badge, Field, Modal, PageHeader, Toggle, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDuration, fmtPct, fmtRelative } from '../utils/format.ts';

const LLM_ROLES: PipelineRole[] = ['claim_extraction', 'answer_generation'];

const STAGE_ICON: Record<PipelineRole, IconName> = {
  claim_extraction: 'search',
  answer_generation: 'channels',
  embedding: 'database',
  ocr: 'eye',
  transcription: 'bell',
  reverse_image: 'repeat',
};


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

interface Draft {
  providerId: string;
  fallbackId: string;
  timeoutS: number;
  maxRetries: number;
  temperature?: number;
}

export default function ModelsPage() {
  const api = getApi();
  const { can } = useAuth();
  const providers = useAsync(() => api.listProviders(), []);
  const assignments = useAsync(() => api.listAssignments(), []);
  const { run, busy } = useAction();
  const [editing, setEditing] = useState<PipelineAssignment | null>(null);
  const [draft, setDraft] = useState<Draft>({ providerId: '', fallbackId: '', timeoutS: 30, maxRetries: 2 });
  const [tests, setTests] = useState<Record<string, ProviderTestResult>>({});
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<ProviderInput>(EMPTY_PROVIDER);
  const writable = can('models:write');

  const list = providers.data ?? [];
  const byId = new Map(list.map((p) => [p.id, p]));

  const openEdit = (a: PipelineAssignment) => {
    setDraft({
      providerId: a.providerId ?? '',
      fallbackId: a.fallbackProviderIds[0] ?? '',
      timeoutS: a.params.timeoutS,
      maxRetries: a.params.maxRetries,
      temperature: a.params.temperature,
    });
    setEditing(a);
  };

  const replaceAssignment = (next: PipelineAssignment) =>
    assignments.setData((l) => (l ?? []).map((a) => (a.role === next.role ? next : a)));

  const save = async () => {
    if (!editing) return;
    const ok = await run(async () => {
      replaceAssignment(
        await api.updateAssignment(editing.role, {
          providerId: draft.providerId || null,
          fallbackProviderIds: draft.fallbackId && draft.fallbackId !== draft.providerId ? [draft.fallbackId] : [],
          params: { timeoutS: draft.timeoutS, maxRetries: draft.maxRetries, temperature: draft.temperature },
        }),
      );
    }, 'Model zmieniony. Nowe zapytania korzystają już z wybranego modelu.');
    if (ok) setEditing(null);
  };

  const test = (p: ModelProvider) =>
    run(async () => {
      const result = await api.testProvider(p.id);
      setTests((t) => ({ ...t, [p.id]: result }));
    });

  const addProvider = async (e: FormEvent) => {
    e.preventDefault();
    let created: ModelProvider | null = null;
    const ok = await run(async () => {
      created = await api.createProvider({ ...form, keyRef: form.keyRef?.trim() || undefined });
    }, 'Model dodany. Klucz API ustawia się na serwerze — potem kliknij „Sprawdź”.');
    if (ok && created) {
      providers.setData((l) => [...(l ?? []), created as ModelProvider]);
      setAdding(false);
      setForm(EMPTY_PROVIDER);
    }
  };

  const remove = async (p: ModelProvider) => {
    if (await run(() => api.deleteProvider(p.id), 'Model usunięty z listy.')) {
      providers.setData((l) => (l ?? []).filter((x) => x.id !== p.id));
    }
  };

  const candidates = editing ? list.filter((p) => p.roles.includes(editing.role)) : [];
  const chosen = byId.get(draft.providerId);

  return (
    <>
      <PageHeader
        title="Modele AI"
        description="Wybierz, który model obsługuje każdy etap sprawdzania informacji. Zmiana działa od razu i nie wymaga przebudowy systemu."
        actions={
          writable && (
            <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
              <Icon name="plus" size={16} /> Dodaj model
            </button>
          )
        }
      />

      <Async state={assignments}>
        {(stages) => (
          <>
            <RegionNotice stages={stages} byId={byId} />
            <section className="stage-list" aria-label="Etapy sprawdzania">
              {stages.map((a, i) => {
                const p = a.providerId ? byId.get(a.providerId) : undefined;
                const fallback = a.fallbackProviderIds.map((id) => byId.get(id)?.name ?? id)[0];
                return (
                  <article key={a.role} className={`stage ${a.enabled && p ? '' : 'is-off'}`}>
                    <div className="stage-step" aria-hidden="true">
                      <Icon name={STAGE_ICON[a.role]} size={18} />
                      <span>{i + 1}</span>
                    </div>
                    <div className="stage-info">
                      <h3>{PIPELINE_ROLE[a.role].label}</h3>
                      <p className="muted small">{PIPELINE_ROLE[a.role].description}</p>
                    </div>
                    <div className="stage-model">
                      {a.enabled && p ? (
                        <>
                          <div className="stage-model-name">
                            <span className={`status-dot dot-${HEALTH[p.health].tone}`} title={HEALTH[p.health].label} />
                            {p.name}
                          </div>
                          <div className="row gap-xs wrap">
                            <Badge tone={REGION[p.region].tone}>{REGION[p.region].label}</Badge>
                            {p.health !== 'ok' && <Badge tone={HEALTH[p.health].tone}>{HEALTH[p.health].label}</Badge>}
                            <span className="muted small">
                              {p.latencyP50Ms ? `~${fmtDuration(p.latencyP50Ms)}` : ''}
                              {fallback ? ` · zapasowy: ${fallback}` : ' · bez zapasowego'}
                            </span>
                          </div>
                        </>
                      ) : (
                        <span className="muted">{a.enabled ? 'Nie wybrano modelu' : 'Etap wyłączony'}</span>
                      )}
                    </div>
                    <div className="stage-actions">
                      {writable ? (
                        <>
                          <button type="button" className="btn btn-sm btn-primary" onClick={() => openEdit(a)}>
                            {p ? 'Zmień' : 'Wybierz model'}
                          </button>
                          <Toggle
                            checked={a.enabled}
                            label={<span className="sr-only">{a.enabled ? 'Wyłącz etap' : 'Włącz etap'}</span>}
                            disabled={busy || !a.providerId}
                            onChange={(enabled) =>
                              run(async () => replaceAssignment(await api.updateAssignment(a.role, { enabled })), enabled ? 'Etap włączony.' : 'Etap wyłączony.')
                            }
                          />
                        </>
                      ) : (
                        <Badge tone={a.enabled ? 'good' : 'muted'}>{a.enabled ? 'Włączony' : 'Wyłączony'}</Badge>
                      )}
                    </div>
                  </article>
                );
              })}
            </section>
          </>
        )}
      </Async>

      <section>
        <div className="section-head">
          <h2>Dostępne modele</h2>
          <p className="muted small">Modele, które można przypisać do etapów. Klucze API są tylko na serwerze — tu widać, czy są ustawione.</p>
        </div>
        <Async state={providers}>
          {(items) => (
            <div className="provider-grid">
              {items.map((p) => {
                const usedIn = (assignments.data ?? []).filter((a) => a.providerId === p.id).map((a) => PIPELINE_ROLE[a.role].label);
                const backupIn = (assignments.data ?? []).filter((a) => a.fallbackProviderIds.includes(p.id));
                const t = tests[p.id];
                return (
                  <article key={p.id} className="provider-card">
                    <header>
                      <div>
                        <h3>{p.name}</h3>
                        <span className="muted small">{p.vendor}</span>
                      </div>
                      <span className={`status-dot dot-${HEALTH[p.health].tone}`} title={HEALTH[p.health].label} />
                    </header>
                    <div className="row gap-xs wrap">
                      <Badge tone={REGION[p.region].tone}>{REGION[p.region].label}</Badge>
                      <Badge tone={HEALTH[p.health].tone}>{HEALTH[p.health].label}</Badge>
                      {!p.keyConfigured && <Badge tone="warning">Brak klucza API</Badge>}
                    </div>
                    <p className="small provider-use">
                      {usedIn.length ? (
                        <>
                          <Icon name="check" size={14} /> Używany: {usedIn.join(', ')}
                        </>
                      ) : backupIn.length ? (
                        'Model zapasowy'
                      ) : (
                        <span className="muted">Obecnie nieużywany</span>
                      )}
                    </p>
                    {p.errorRate !== undefined && (
                      <p className="small muted">Błędy: {fmtPct(p.errorRate, 1)}</p>
                    )}
                    {t && (
                      <div className={`notice ${t.ok ? 'notice-good' : 'notice-critical'} small`}>
                        <Icon name={t.ok ? 'check' : 'alert'} size={14} />
                        <span>{t.ok ? `Działa (${fmtDuration(t.latencyMs)}). ` : ''}{t.message}</span>
                      </div>
                    )}
                    <details className="provider-details">
                      <summary>Szczegóły techniczne</summary>
                      <dl className="kv small">
                        <dt>Model</dt>
                        <dd className="mono">{p.model}</dd>
                        <dt>Protokół</dt>
                        <dd>{PROTOCOL[p.protocol]}</dd>
                        <dt>Adres</dt>
                        <dd className="mono break">{p.baseUrl}</dd>
                        <dt>Klucz</dt>
                        <dd>{p.keyRef ? <span className="mono">{p.keyRef}</span> : 'niewymagany'}</dd>
                        <dt>Sprawdzono</dt>
                        <dd>{p.lastCheckedAt ? fmtRelative(p.lastCheckedAt) : 'nigdy'}</dd>
                      </dl>
                      {p.notes && <p className="muted small">{p.notes}</p>}
                    </details>
                    <footer>
                      <button type="button" className="btn btn-sm" disabled={busy} onClick={() => test(p)}>
                        <Icon name="plug" size={14} /> Sprawdź
                      </button>
                      {writable && usedIn.length === 0 && backupIn.length === 0 && (
                        <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => remove(p)}>
                          Usuń
                        </button>
                      )}
                    </footer>
                  </article>
                );
              })}
            </div>
          )}
        </Async>
      </section>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing ? `Model dla etapu: ${PIPELINE_ROLE[editing.role].label}` : ''}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setEditing(null)}>
              Anuluj
            </button>
            <button type="button" className="btn btn-primary" disabled={busy || !draft.providerId} onClick={save}>
              Użyj tego modelu
            </button>
          </>
        }
      >
        {editing && (
          <div className="form-grid">
            <div className="option-list" role="radiogroup" aria-label="Model główny">
              {candidates.map((p) => {
                const disabled = !p.keyConfigured;
                const selected = draft.providerId === p.id;
                return (
                  <label key={p.id} className={`option ${selected ? 'is-selected' : ''} ${disabled ? 'is-disabled' : ''}`}>
                    <input
                      type="radio"
                      name="provider"
                      value={p.id}
                      checked={selected}
                      disabled={disabled}
                      onChange={() => setDraft({ ...draft, providerId: p.id, fallbackId: draft.fallbackId === p.id ? '' : draft.fallbackId })}
                    />
                    <span className="option-body">
                      <span className="option-title">
                        {p.name}
                        {editing.providerId === p.id && <Badge tone="info">obecny</Badge>}
                      </span>
                      <span className="row gap-xs wrap">
                        <Badge tone={REGION[p.region].tone}>{REGION[p.region].label}</Badge>
                        <Badge tone={HEALTH[p.health].tone}>{HEALTH[p.health].label}</Badge>
                      </span>
                      {disabled && <span className="small text-critical">Brak klucza API — administrator musi go dodać na serwerze.</span>}
                    </span>
                  </label>
                );
              })}
            </div>

            {chosen?.region === 'poza_EOG' && (
              <div className="notice notice-warning">
                <Icon name="alert" size={16} />
                <span>
                  Ten model przetwarza dane <strong>poza EOG</strong>. Treść zapytań (po zamaskowaniu danych osobowych)
                  opuści EOG.
                </span>
              </div>
            )}

            <Field label="Model zapasowy" hint="Używany automatycznie, gdy główny nie odpowiada.">
              <select value={draft.fallbackId} onChange={(e) => setDraft({ ...draft, fallbackId: e.target.value })}>
                <option value="">— brak —</option>
                {candidates
                  .filter((p) => p.id !== draft.providerId && p.keyConfigured)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({REGION[p.region].label})
                    </option>
                  ))}
              </select>
            </Field>

            <details className="provider-details">
              <summary>Ustawienia zaawansowane</summary>
              <div className="form-row">
                <Field label="Limit czasu (s)">
                  <input type="number" min={1} max={120} value={draft.timeoutS} onChange={(e) => setDraft({ ...draft, timeoutS: Number(e.target.value) })} />
                </Field>
                <Field label="Ponowienia">
                  <input type="number" min={0} max={5} value={draft.maxRetries} onChange={(e) => setDraft({ ...draft, maxRetries: Number(e.target.value) })} />
                </Field>
                {LLM_ROLES.includes(editing.role) && (
                  <Field label="Temperatura">
                    <input type="number" min={0} max={1} step={0.1} value={draft.temperature ?? 0} onChange={(e) => setDraft({ ...draft, temperature: Number(e.target.value) })} />
                  </Field>
                )}
              </div>
            </details>
            <p className="muted small">Zmiana trafi do dziennika audytu. Po zmianie warto uruchomić testy referencyjne.</p>
          </div>
        )}
      </Modal>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="Dodaj model"
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
            <Field label="Nazwa">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={80} placeholder="np. Mistral Small" />
            </Field>
            <Field label="Dostawca">
              <input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} maxLength={80} />
            </Field>
          </div>
          <div className="form-row">
            <Field label="Identyfikator modelu">
              <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} required placeholder="np. mistral-small-latest" maxLength={120} />
            </Field>
            <Field label="Gdzie przetwarza dane">
              <select value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value as ProcessingRegion })}>
                {Object.entries(REGION).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <fieldset className="fieldset">
            <legend className="field-label">Do czego może służyć</legend>
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
          <details className="provider-details">
            <summary>Połączenie i koszty</summary>
            <div className="form-grid">
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
                <Field label="Nazwa sekretu z kluczem" hint="Sam klucz dodaje się na serwerze.">
                  <input value={form.keyRef} onChange={(e) => setForm({ ...form, keyRef: e.target.value.toUpperCase() })} placeholder="np. MISTRAL_API_KEY" maxLength={64} />
                </Field>
              </div>
              <Field label="Adres API">
                <input value={form.baseUrl} onChange={(e) => setForm({ ...form, baseUrl: e.target.value })} required maxLength={200} />
              </Field>
              <div className="form-row">
                <Field label="Koszt wejścia (zł / 1k tokenów)">
                  <input type="number" min={0} step={0.0001} value={form.costPer1kInputPln} onChange={(e) => setForm({ ...form, costPer1kInputPln: Number(e.target.value) })} />
                </Field>
                <Field label="Koszt wyjścia (zł / 1k tokenów)">
                  <input type="number" min={0} step={0.0001} value={form.costPer1kOutputPln} onChange={(e) => setForm({ ...form, costPer1kOutputPln: Number(e.target.value) })} />
                </Field>
              </div>
            </div>
          </details>
        </form>
      </Modal>
    </>
  );
}

function RegionNotice({ stages, byId }: { stages: PipelineAssignment[]; byId: Map<string, ModelProvider> }) {
  const outside = stages.filter((a) => a.enabled && a.providerId && byId.get(a.providerId)?.region === 'poza_EOG');
  return outside.length === 0 ? (
    <div className="notice notice-good">
      <Icon name="shield" size={16} />
      <span>Dane są przetwarzane w EOG lub na własnych serwerach.</span>
    </div>
  ) : (
    <div className="notice notice-warning">
      <Icon name="alert" size={16} />
      <span>
        Przetwarzanie poza EOG: <strong>{outside.map((a) => PIPELINE_ROLE[a.role].label).join(', ')}</strong>.
      </span>
    </div>
  );
}
