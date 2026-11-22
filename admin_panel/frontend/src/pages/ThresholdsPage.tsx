import { useState } from 'react';
import { fieldLabel, formatValue } from '../api/backend/mappers.ts';
import { getApi } from '../api/index.ts';
import type { MonitoringSettings, RuntimeConfig } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { Async, Card, Field, Modal, PageHeader, Toggle, useAction, useToast } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime } from '../utils/format.ts';

type NumberKey = {
  [K in keyof MonitoringSettings]: MonitoringSettings[K] extends number ? K : never;
}[keyof MonitoringSettings];

interface NumberField {
  key: NumberKey;
  label: string;
  hint: string;
  min: number;
  max: number;
  unit?: string;
}

const GROUPS: { title: string; subtitle: string; fields: NumberField[] }[] = [
  {
    title: 'Luka informacyjna',
    subtitle:
      'Temat bez rozstrzygnięcia (brak źródeł albo niewystarczające dane) staje się luką, gdy pyta o niego dość różnych osób. Pierwsze rozstrzygnięcie oparte na źródłach zamyka lukę automatycznie.',
    fields: [
      { key: 'info_gap_min_users', label: 'Różne osoby', hint: 'tyle osób musi zapytać o ten sam temat', min: 1, max: 10_000 },
      { key: 'info_gap_window_hours', label: 'Okno czasu', hint: 'w jakim okresie liczymy pytania', min: 1, max: 8760, unit: 'h' },
    ],
  },
  {
    title: 'Możliwy atak dezinformacyjny',
    subtitle: 'Wiele różnych osób w krótkim czasie pyta o twierdzenie ocenione jako fałsz. Od dwukrotności progu alert ma wysoki priorytet.',
    fields: [
      { key: 'disinfo_min_users', label: 'Różne osoby', hint: 'próg alertu', min: 2, max: 100_000 },
      { key: 'disinfo_window_hours', label: 'Okno czasu', hint: 'w jakim okresie liczymy pytania', min: 1, max: 2160, unit: 'h' },
    ],
  },
  {
    title: 'Treści niebezpieczne',
    subtitle:
      'Terroryzm, materiały wybuchowe, broń, broń masowego rażenia, przemoc masowa. Pytanie o fakt jest sprawdzane i oznaczane; prośba o instrukcję lub zdobycie to wysokie ryzyko.',
    fields: [
      { key: 'dangerous_alert_after', label: 'Alert po', hint: 'zapytaniach o treści niebezpieczne jednej osoby', min: 1, max: 1000 },
      { key: 'dangerous_block_after', label: 'Blokada po', hint: 'zapytaniach wysokiego ryzyka jednej osoby', min: 1, max: 1000 },
      { key: 'dangerous_window_hours', label: 'Okno czasu', hint: 'dla obu progów powyżej', min: 1, max: 2160, unit: 'h' },
      { key: 'dangerous_block_hours', label: 'Długość blokady', hint: 'automatycznej', min: 1, max: 8760, unit: 'h' },
    ],
  },
];

export default function ThresholdsPage() {
  const api = getApi();
  const config = useAsync(() => api.getRuntimeConfig(), []);
  return (
    <>
      <PageHeader
        title="Reguły i progi"
        description="Kiedy backend tworzy alerty o lukach informacyjnych, możliwej dezinformacji i niebezpiecznych użytkownikach, kiedy blokuje, i jak długo przechowuje zapytania. Zmiany działają od następnego zapytania."
      />
      <Async state={config}>
        {/* Keyed by the saved values: after a save the form starts from the new config. */}
        {(c) => <ThresholdsForm key={JSON.stringify(c.monitoring)} config={c} onSaved={config.setData} />}
      </Async>
    </>
  );
}

function ThresholdsForm({ config, onSaved }: { config: RuntimeConfig; onSaved: (c: RuntimeConfig) => void }) {
  const api = getApi();
  const toast = useToast();
  const { can } = useAuth();
  const editable = can('rules:write');
  const { run, busy } = useAction();
  const [form, setForm] = useState<MonitoringSettings>(config.monitoring);
  const [purging, setPurging] = useState(false);
  const [purgeDays, setPurgeDays] = useState(String(config.monitoring.retention_days));

  const invalid = GROUPS.flatMap((g) => g.fields)
    .concat([{ key: 'retention_days', label: '', hint: '', min: 1, max: 3650 }])
    .some((f) => !Number.isInteger(form[f.key]) || form[f.key] < f.min || form[f.key] > f.max);
  const dirty = JSON.stringify(form) !== JSON.stringify(config.monitoring);

  const save = async () => {
    let summary = '';
    const ok = await run(async () => {
      const result = await api.updateRuntimeConfig({ monitoring: form });
      summary = result.changes.map((c) => `${fieldLabel(c.field)}: ${formatValue(c.new)}`).join('; ');
      onSaved(result.config);
    });
    if (ok) toast(summary ? 'good' : 'info', summary ? `Zapisano: ${summary}.` : 'Bez zmian.');
  };

  const purge = async () => {
    const days = Number(purgeDays);
    let message = '';
    const ok = await run(async () => {
      const result = await api.purgeOldData(days);
      message = `Usunięto ${result.deleted.queries} zapytań i ${result.deleted.claims} twierdzeń starszych niż ${fmtDateTime(result.before)}.`;
    });
    if (ok) {
      toast('good', message);
      setPurging(false);
    }
  };

  const setNumber = (key: NumberKey, value: string) => setForm((f) => ({ ...f, [key]: value === '' ? Number.NaN : Number(value) }));

  return (
    <div className="stack">
      {GROUPS.map((group) => (
        <Card key={group.title} title={group.title} subtitle={group.subtitle}>
          <div className="form-cols">
            {group.fields.map((f) => (
              <Field key={f.key} label={`${f.label}${f.unit ? ` (${f.unit})` : ''}`} hint={`${f.hint} · ${f.min}–${f.max}`}>
                <input
                  type="number"
                  min={f.min}
                  max={f.max}
                  step={1}
                  value={Number.isNaN(form[f.key]) ? '' : form[f.key]}
                  disabled={!editable}
                  onChange={(e) => setNumber(f.key, e.target.value)}
                />
              </Field>
            ))}
          </div>
          {group.title === 'Treści niebezpieczne' && (
            <div className="stack">
              <Toggle
                checked={form.auto_block}
                disabled={!editable}
                onChange={(v) => setForm({ ...form, auto_block: v })}
                label="Automatyczna blokada"
                description="Po przekroczeniu progu zapytań wysokiego ryzyka użytkownik jest czasowo blokowany."
              />
              <Toggle
                checked={form.refuse_high_risk}
                disabled={!editable}
                onChange={(v) => setForm({ ...form, refuse_high_risk: v })}
                label="Odrzucaj prośby wysokiego ryzyka"
                description="Prośby o instrukcje lub zdobycie broni i materiałów wybuchowych nie są przetwarzane."
              />
            </div>
          )}
        </Card>
      ))}

      <Card
        title="Retencja danych"
        subtitle="Zapytania i twierdzenia starsze niż limit są usuwane przy starcie panelu. Można je też usunąć ręcznie."
        actions={
          can('settings:write') && (
            <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => setPurging(true)}>
              <Icon name="trash" size={14} /> Usuń stare dane
            </button>
          )
        }
      >
        <div className="form-cols">
          <Field label="Przechowuj zapytania (dni)" hint="1–3650">
            <input
              type="number"
              min={1}
              max={3650}
              step={1}
              value={Number.isNaN(form.retention_days) ? '' : form.retention_days}
              disabled={!editable}
              onChange={(e) => setNumber('retention_days', e.target.value)}
            />
          </Field>
        </div>
      </Card>

      {editable && (
        <div className="row gap-sm">
          <button type="button" className="btn btn-primary" disabled={busy || !dirty || invalid} onClick={save}>
            Zapisz reguły
          </button>
          <button type="button" className="btn btn-ghost" disabled={busy || !dirty} onClick={() => setForm(config.monitoring)}>
            Cofnij zmiany
          </button>
          {invalid && <span className="field-error">Popraw wartości spoza dozwolonego zakresu.</span>}
        </div>
      )}

      <Modal
        open={purging}
        onClose={() => setPurging(false)}
        title="Usunąć stare zapytania?"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setPurging(false)}>
              Anuluj
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !Number.isInteger(Number(purgeDays)) || Number(purgeDays) < 1}
              onClick={purge}
            >
              Usuń trwale
            </button>
          </>
        }
      >
        <p>Zapytania użytkowników i ich twierdzenia starsze niż podana liczba dni zostaną trwale usunięte.</p>
        <Field label="Starsze niż (dni)">
          <input type="number" min={1} max={3650} value={purgeDays} onChange={(e) => setPurgeDays(e.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}
