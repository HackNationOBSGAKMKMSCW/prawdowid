import { useId, useState } from 'react';
import { fieldLabel, formatValue, SECRET_LABEL } from '../api/backend/mappers.ts';
import { getApi } from '../api/index.ts';
import type { ApiSettings, AvailableModels, ConfigChange, LlmSettings, RuntimeConfig, RuntimeConfigPatch, SecretName } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { Async, Badge, Card, Field, PageHeader, Toggle, useAction, useToast } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';

/** Text field → override: empty means "use the value from .env" (null). */
const orNull = (value: string) => (value.trim() === '' ? null : value.trim());
const numOrNull = (value: string) => (value.trim() === '' ? null : Number(value));

function EnvHint({ config, env }: { config: RuntimeConfig; env: string }) {
  const value = config.effective[env];
  return (
    <>
      Teraz używane: <code>{value ?? '(nie ustawiono)'}</code> · <span className="mono">{env}</span>
    </>
  );
}

function summarize(changes: ConfigChange[]): string {
  if (!changes.length) return 'Bez zmian.';
  return `Zapisano: ${changes.map((c) => `${fieldLabel(c.field)}: ${formatValue(c.new)}`).join('; ')}.`;
}

export default function RuntimeConfigPage() {
  const api = getApi();
  const config = useAsync(() => api.getRuntimeConfig(), []);

  return (
    <>
      <PageHeader
        title="Modele i źródła danych"
        description="Model językowy, źródła danych i klucze API używane przez backend. Zmiany działają od następnego zapytania, bez restartu, także w bocie WhatsApp. Puste pole = wartość z pliku .env."
      />
      <Async state={config}>
        {(c) => (
          <div className="stack">
            {/* Keyed by the saved values: after a save the form starts from the new config. */}
            <LlmCard key={JSON.stringify(c.llm)} config={c} onSaved={config.setData} />
            <ApisCard config={c} onSaved={config.setData} />
            <SecretsCard config={c} onSaved={config.setData} />
            <p className="muted small">
              Nadpisania są zapisane w <code>{c.file}</code>. Każda zmiana trafia do dziennika audytu.
            </p>
          </div>
        )}
      </Async>
    </>
  );
}

function useSave(onSaved: (config: RuntimeConfig) => void) {
  const api = getApi();
  const toast = useToast();
  const { run, busy } = useAction();
  const save = async (patch: RuntimeConfigPatch) => {
    let changes: ConfigChange[] = [];
    const ok = await run(async () => {
      const result = await api.updateRuntimeConfig(patch);
      changes = result.changes;
      onSaved(result.config);
    });
    if (ok) toast(changes.length ? 'good' : 'info', summarize(changes));
    return ok;
  };
  return { save, busy };
}

function LlmCard({ config, onSaved }: { config: RuntimeConfig; onSaved: (c: RuntimeConfig) => void }) {
  const api = getApi();
  const { can } = useAuth();
  const editable = can('models:write');
  const listId = useId();
  const { save, busy } = useSave(onSaved);
  const { run, busy: loadingModels } = useAction();
  const [models, setModels] = useState<AvailableModels | null>(null);
  const [form, setForm] = useState(() => toForm(config.llm));

  const loadModels = () =>
    run(async () => {
      setModels(await api.listAvailableModels());
    });

  const dirty = JSON.stringify(fromForm(form)) !== JSON.stringify(config.llm);

  return (
    <Card
      title="Model językowy"
      subtitle="Endpoint zgodny z API OpenAI. Model główny obsługuje analizę tekstu i werdykt; osobny model analizy tekstu jest opcjonalny."
      actions={
        <button type="button" className="btn btn-sm" disabled={loadingModels} onClick={loadModels}>
          <Icon name="refresh" size={14} /> Pobierz listę modeli
        </button>
      }
    >
      {models && (
        <div className={`notice ${models.error ? 'notice-warning' : 'notice-info'}`}>
          <Icon name={models.error ? 'alert' : 'info'} size={16} />
          <div>
            {models.error
              ? `Dostawca nie odpowiedział (${models.error}). Nazwę modelu można wpisać ręcznie.`
              : `Dostawca ${models.baseUrl ?? ''} udostępnia ${models.models.length} modeli — podpowiedzi pojawią się w polach poniżej.`}
          </div>
        </div>
      )}
      <datalist id={listId}>
        {(models?.models ?? []).map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <div className="form-cols">
        <Field label="Model główny" hint={<EnvHint config={config} env="FREELLM_MODEL" />}>
          <input type="text" list={listId} value={form.model} disabled={!editable} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="z .env" />
        </Field>
        <Field label="Model analizy tekstu (opcjonalnie)" hint={<EnvHint config={config} env="TEXT_ANALYSIS_MODEL" />}>
          <input type="text" list={listId} value={form.text_analysis_model} disabled={!editable} onChange={(e) => setForm({ ...form, text_analysis_model: e.target.value })} placeholder="jak model główny" />
        </Field>
        <Field label="Adres API (base URL)" hint={<EnvHint config={config} env="FREELLM_BASE_URL" />}>
          <input type="url" value={form.base_url} disabled={!editable} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://…/v1" />
        </Field>
        <Field label="Limit czasu (s)" hint={<EnvHint config={config} env="FREELLM_TIMEOUT" />}>
          <input type="number" min={1} max={600} value={form.timeout_s} disabled={!editable} onChange={(e) => setForm({ ...form, timeout_s: e.target.value })} placeholder="z .env" />
        </Field>
        <Field label="Ponowienia" hint={<EnvHint config={config} env="FREELLM_MAX_RETRIES" />}>
          <input type="number" min={0} max={10} value={form.max_retries} disabled={!editable} onChange={(e) => setForm({ ...form, max_retries: e.target.value })} placeholder="z .env" />
        </Field>
      </div>
      {editable && (
        <div className="row gap-sm">
          <button type="button" className="btn btn-primary" disabled={busy || !dirty} onClick={() => save({ llm: fromForm(form) })}>
            Zapisz model
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy || Object.values(config.llm).every((v) => v === null)}
            onClick={() => save({ llm: { model: null, text_analysis_model: null, base_url: null, timeout_s: null, max_retries: null } })}
          >
            Przywróć wartości z .env
          </button>
        </div>
      )}
    </Card>
  );
}

type LlmForm = Record<keyof LlmSettings, string>;

function toForm(llm: LlmSettings): LlmForm {
  return {
    model: llm.model ?? '',
    text_analysis_model: llm.text_analysis_model ?? '',
    base_url: llm.base_url ?? '',
    timeout_s: llm.timeout_s === null ? '' : String(llm.timeout_s),
    max_retries: llm.max_retries === null ? '' : String(llm.max_retries),
  };
}

function fromForm(form: LlmForm): LlmSettings {
  return {
    model: orNull(form.model),
    text_analysis_model: orNull(form.text_analysis_model),
    base_url: orNull(form.base_url),
    timeout_s: numOrNull(form.timeout_s),
    max_retries: numOrNull(form.max_retries),
  };
}

const CLIENT_LABEL: Record<string, string> = {
  google_fact_check: 'Google Fact Check Tools',
  sejm: 'Sejm RP (API)',
  sejm_eli: 'Sejm — akty prawne (ELI)',
  eurlex: 'EUR-Lex',
  dane_gov: 'dane.gov.pl',
};

function ApisCard({ config, onSaved }: { config: RuntimeConfig; onSaved: (c: RuntimeConfig) => void }) {
  const { can } = useAuth();
  const editable = can('models:write');
  const { save, busy } = useSave(onSaved);
  const envDisabled = (config.effective.API_READING_DISABLED_CLIENTS ?? '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  const disabled = config.apis.disabled_clients ?? envDisabled;

  const toggleClient = (name: string, enabled: boolean) => {
    const next = enabled ? disabled.filter((n) => n !== name) : [...new Set([...disabled, name])];
    void save({ apis: { disabled_clients: next } });
  };

  const setApis = (patch: Partial<ApiSettings>) => void save({ apis: patch });

  return (
    <Card
      title="Źródła danych"
      subtitle="Klienci apiReading, z których backend szuka materiałów do weryfikacji, oraz pobieranie treści artykułów."
    >
      <div className="stack">
        <div className="row gap-sm wrap">
          {config.apis.disabled_clients === null ? (
            <Badge tone="muted">Lista z .env</Badge>
          ) : (
            <Badge tone="info">Nadpisane w panelu</Badge>
          )}
          {editable && config.apis.disabled_clients !== null && (
            <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setApis({ disabled_clients: null })}>
              Przywróć listę z .env
            </button>
          )}
        </div>
        {config.apiClients.length === 0 && <p className="muted small">Backend nie zgłosił żadnych klientów API.</p>}
        {config.apiClients.map((name) => (
          <Toggle
            key={name}
            checked={!disabled.includes(name)}
            disabled={!editable || busy}
            onChange={(on) => toggleClient(name, on)}
            label={CLIENT_LABEL[name] ?? name}
            description={<span className="mono">{name}</span>}
          />
        ))}

        <h3 className="subhead">Pobieranie artykułów z linków</h3>
        <div className="form-cols">
          <Field label="Pobieranie treści" hint={<EnvHint config={config} env="ARTICLE_SCRAPING_ENABLED" />}>
            <select
              value={config.apis.article_scraping_enabled === null ? 'env' : String(config.apis.article_scraping_enabled)}
              disabled={!editable || busy}
              onChange={(e) => setApis({ article_scraping_enabled: e.target.value === 'env' ? null : e.target.value === 'true' })}
            >
              <option value="env">Jak w .env</option>
              <option value="true">Włączone</option>
              <option value="false">Wyłączone</option>
            </select>
          </Field>
          <Field label="Ekstraktor" hint={<EnvHint config={config} env="ARTICLE_EXTRACTOR" />}>
            <select
              value={config.apis.article_extractor ?? 'env'}
              disabled={!editable || busy}
              onChange={(e) => setApis({ article_extractor: e.target.value === 'env' ? null : (e.target.value as 'local' | 'diffbot') })}
            >
              <option value="env">Jak w .env</option>
              <option value="local">Lokalny (trafilatura)</option>
              <option value="diffbot">Diffbot (wymaga klucza)</option>
            </select>
          </Field>
        </div>
      </div>
    </Card>
  );
}

function SecretsCard({ config, onSaved }: { config: RuntimeConfig; onSaved: (c: RuntimeConfig) => void }) {
  const { can } = useAuth();
  const editable = can('models:write');
  const { save, busy } = useSave(onSaved);
  const [values, setValues] = useState<Partial<Record<SecretName, string>>>({});
  const names = Object.keys(config.secrets) as SecretName[];

  const store = async (name: SecretName, value: string | null) => {
    if (await save({ secrets: { [name]: value } })) setValues((v) => ({ ...v, [name]: '' }));
  };

  return (
    <Card
      title="Klucze API"
      subtitle="Tylko do zapisu: panel nigdy nie odczytuje klucza, pokazuje wyłącznie jego końcówkę. Usunięcie nadpisania przywraca klucz z .env."
    >
      <ul className="list">
        {names.map((name) => {
          const s = config.secrets[name];
          return (
            <li key={name} className="secret-row">
              <div className="list-main">
                <span className="list-title">{SECRET_LABEL[name] ?? name}</span>
                <span className="row gap-sm wrap">
                  {s.set ? <Badge tone="good">Ustawiony {s.mask ?? ''}</Badge> : <Badge tone="warning">Brak klucza</Badge>}
                  {s.overridden && <Badge tone="info">Nadpisany w panelu</Badge>}
                </span>
              </div>
              {editable && (
                <div className="row gap-sm wrap">
                  <input
                    type="password"
                    autoComplete="new-password"
                    aria-label={`Nowy klucz: ${SECRET_LABEL[name] ?? name}`}
                    placeholder="Nowy klucz"
                    value={values[name] ?? ''}
                    onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
                  />
                  <button type="button" className="btn btn-sm btn-primary" disabled={busy || !(values[name] ?? '').trim()} onClick={() => store(name, (values[name] ?? '').trim())}>
                    Zapisz
                  </button>
                  {s.overridden && (
                    <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => store(name, null)}>
                      Usuń nadpisanie
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
