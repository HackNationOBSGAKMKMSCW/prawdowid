import { type FormEvent, useState } from 'react';
import { getApi } from '../api/index.ts';
import type { Source, SourceInput, SourceStatus, SourceType } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { SOURCE_STATUS, SOURCE_TYPE, TIER } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, Field, Kpi, Modal, PageHeader, SearchInput, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtInt, fmtRelative } from '../utils/format.ts';

const EMPTY: SourceInput = {
  name: '',
  url: 'https://',
  type: 'official',
  tier: 'A',
  language: 'pl',
  license: '',
  updateFrequency: 'codziennie',
  qualification: '',
};

export default function SourcesPage() {
  const api = getApi();
  const { can } = useAuth();
  const sources = useAsync(() => api.listSources(), []);
  const { run, busy } = useAction();
  const [search, setSearch] = useState('');
  const [type, setType] = useState<SourceType | 'any'>('any');
  const [status, setStatus] = useState<SourceStatus | 'any'>('any');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<SourceInput>(EMPTY);
  const [changing, setChanging] = useState<{ source: Source; status: SourceStatus } | null>(null);
  const [note, setNote] = useState('');

  const all = sources.data ?? [];
  const active = all.filter((s) => s.status === 'active');
  const domains = new Set(active.map((s) => s.domain));
  const types = new Set(active.map((s) => s.type));
  const docs = active.reduce((sum, s) => sum + s.documents, 0);
  const rows = all.filter(
    (s) =>
      (type === 'any' || s.type === type) &&
      (status === 'any' || s.status === status) &&
      (!search.trim() || `${s.name} ${s.domain}`.toLowerCase().includes(search.trim().toLowerCase())),
  );

  const replace = (updated: Source) => sources.setData((list) => (list ?? []).map((s) => (s.id === updated.id ? updated : s)));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let created: Source | null = null;
    const ok = await run(async () => {
      created = await api.createSource(form);
    }, 'Źródło dodane do katalogu.');
    if (ok && created) {
      sources.setData((list) => [...(list ?? []), created as Source]);
      setAdding(false);
      setForm(EMPTY);
    }
  };

  return (
    <>
      <PageHeader
        title="Katalog źródeł"
        description="Otwarty, audytowalny katalog: każde źródło ma typ, poziom zaufania, licencję i uzasadnienie kwalifikacji. Status źródła (np. sankcje UE) nie przesądza o prawdziwości konkretnej treści."
        actions={
          <>
            {can('export') && (
              <>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() =>
                    exportCsv('katalog-zrodel', all, [
                      { header: 'nazwa', value: (s) => s.name },
                      { header: 'url', value: (s) => s.url },
                      { header: 'typ', value: (s) => SOURCE_TYPE[s.type] },
                      { header: 'poziom', value: (s) => s.tier },
                      { header: 'licencja', value: (s) => s.license },
                      { header: 'status', value: (s) => SOURCE_STATUS[s.status].label },
                      { header: 'uzasadnienie', value: (s) => s.qualification },
                      { header: 'adnotacja', value: (s) => s.statusNote ?? '' },
                      { header: 'dokumenty', value: (s) => s.documents },
                      { header: 'ostatnie pobranie', value: (s) => s.lastFetchedAt ?? '' },
                    ])
                  }
                >
                  <Icon name="download" size={16} /> CSV
                </button>
                <button type="button" className="btn btn-sm" onClick={() => exportJson('katalog-zrodel', all)}>
                  <Icon name="download" size={16} /> JSON
                </button>
              </>
            )}
            {can('sources:write') && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => setAdding(true)}>
                <Icon name="plus" size={16} /> Dodaj źródło
              </button>
            )}
          </>
        }
      />

      <Async state={sources}>
        {() => (
          <>
            <div className="kpi-grid kpi-grid-4">
              <Kpi icon="database" label="Dokumenty / rekordy" value={fmtInt(docs)} hint={docs >= 100 ? 'wymagane ≥ 100 ✓' : 'wymagane ≥ 100 ✗'} tone={docs >= 100 ? undefined : 'critical'} />
              <Kpi icon="external" label="Domeny" value={domains.size} hint={domains.size >= 10 ? 'wymagane ≥ 10 ✓' : 'wymagane ≥ 10 ✗'} tone={domains.size >= 10 ? undefined : 'critical'} />
              <Kpi icon="sliders" label="Typy źródeł" value={types.size} hint={types.size >= 2 ? 'wymagane ≥ 2 ✓' : 'wymagane ≥ 2 ✗'} tone={types.size >= 2 ? undefined : 'critical'} />
              <Kpi
                icon="alert"
                label="Problemy z pobieraniem"
                value={all.filter((s) => !s.lastFetchOk && s.status !== 'excluded').length}
                tone={all.some((s) => !s.lastFetchOk && s.status !== 'excluded') ? 'warning' : undefined}
                hint="źródła z nieudanym ostatnim pobraniem"
              />
            </div>

            <div className="toolbar">
              <SearchInput value={search} onChange={setSearch} placeholder="Szukaj nazwy lub domeny…" />
              <label className="select-label">
                Typ
                <select value={type} onChange={(e) => setType(e.target.value as SourceType | 'any')}>
                  <option value="any">Wszystkie</option>
                  {Object.entries(SOURCE_TYPE).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="select-label">
                Status
                <select value={status} onChange={(e) => setStatus(e.target.value as SourceStatus | 'any')}>
                  <option value="any">Wszystkie</option>
                  {Object.entries(SOURCE_STATUS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid-2-1">
              <Card padded={false}>
                {rows.length === 0 ? (
                  <EmptyState title="Brak źródeł dla filtrów" icon="database" />
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Źródło</th>
                          <th>Typ / poziom</th>
                          <th>Licencja</th>
                          <th className="num">Dokumenty</th>
                          <th>Pobranie</th>
                          <th>Status</th>
                          {can('sources:write') && <th>Akcje</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((s) => (
                          <tr key={s.id}>
                            <td>
                              <strong>{s.name}</strong>
                              <div className="small">
                                <a href={s.url} target="_blank" rel="noopener noreferrer nofollow">
                                  {s.domain} <Icon name="external" size={11} />
                                </a>
                                <span className="muted"> · {s.language} · aktualizacja {s.updateFrequency}</span>
                              </div>
                              <div className="muted small">{s.qualification}</div>
                              {s.statusNote && <div className="small note-line">{s.statusNote}</div>}
                            </td>
                            <td className="small">
                              {SOURCE_TYPE[s.type]}
                              <div>
                                <Badge tone={s.tier === 'A' ? 'good' : s.tier === 'B' ? 'info' : 'muted'} title={TIER[s.tier]}>
                                  Poziom {s.tier}
                                </Badge>
                              </div>
                            </td>
                            <td className="small">{s.license}</td>
                            <td className="num">{fmtInt(s.documents)}</td>
                            <td className="small nowrap">
                              {s.lastFetchedAt ? (
                                <>
                                  {s.lastFetchOk ? <Badge tone="good">OK</Badge> : <Badge tone="warning">Błąd</Badge>}
                                  <div className="muted">{fmtRelative(s.lastFetchedAt)}</div>
                                </>
                              ) : (
                                <span className="muted">—</span>
                              )}
                            </td>
                            <td>
                              <Badge tone={SOURCE_STATUS[s.status].tone}>{SOURCE_STATUS[s.status].label}</Badge>
                            </td>
                            {can('sources:write') && (
                              <td>
                                <div className="row gap-xs wrap">
                                  {s.status !== 'excluded' && (
                                    <button
                                      type="button"
                                      className="btn btn-xs"
                                      disabled={busy}
                                      onClick={() => run(async () => replace(await api.refreshSource(s.id)), 'Źródło odświeżone.').then(() => sources.reload())}
                                    >
                                      Odśwież
                                    </button>
                                  )}
                                  {s.status === 'active' ? (
                                    <>
                                      <button type="button" className="btn btn-xs" onClick={() => { setNote(''); setChanging({ source: s, status: 'suspended' }); }}>
                                        Zawieś
                                      </button>
                                      <button type="button" className="btn btn-xs btn-ghost" onClick={() => { setNote(''); setChanging({ source: s, status: 'excluded' }); }}>
                                        Wyklucz
                                      </button>
                                    </>
                                  ) : (
                                    <button
                                      type="button"
                                      className="btn btn-xs"
                                      disabled={busy}
                                      onClick={() => run(async () => replace(await api.updateSource(s.id, { status: 'active' })), 'Źródło przywrócone.')}
                                    >
                                      Przywróć
                                    </button>
                                  )}
                                </div>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card title="Zasady kwalifikacji">
                <ul className="bullets small">
                  <li>
                    <strong>Poziom A</strong> — źródła pierwotne i urzędowe (dane.gov.pl, BIP, ISAP, EUR-Lex, komunikaty
                    resortów).
                  </li>
                  <li>
                    <strong>Poziom B</strong> — wiarygodne źródła wtórne: organizacje fact-checkingowe stosujące
                    standardy IFCN/EFCSN, EDMO, bazy incydentów.
                  </li>
                  <li>
                    <strong>Poziom C</strong> — tylko kontekst; nigdy samodzielna podstawa werdyktu.
                  </li>
                  <li>Każde źródło musi mieć licencję pozwalającą na cytowanie oraz uzasadnienie kwalifikacji.</li>
                  <li>Zawieszenie: powtarzające się błędy pobierania lub podejrzenie utraty wiarygodności.</li>
                  <li>
                    Wykluczenie wymaga uzasadnienia i trafia do dziennika audytu. Domena nie przesądza o prawdziwości
                    treści — może tylko wywołać neutralne ostrzeżenie.
                  </li>
                  <li>Przechowywane są: data publikacji i data pobrania każdego dokumentu (aktualność).</li>
                </ul>
              </Card>
            </div>
          </>
        )}
      </Async>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="Dodaj źródło do katalogu"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              Anuluj
            </button>
            <button type="submit" form="source-form" className="btn btn-primary" disabled={busy}>
              Dodaj
            </button>
          </>
        }
      >
        <form id="source-form" className="form-grid" onSubmit={submit}>
          <Field label="Nazwa">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={120} />
          </Field>
          <Field label="Adres URL">
            <input type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
          </Field>
          <Field label="Typ">
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as SourceType })}>
              {Object.entries(SOURCE_TYPE).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Poziom zaufania">
            <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value as Source['tier'] })}>
              {Object.entries(TIER).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Język">
            <input value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} maxLength={20} />
          </Field>
          <Field label="Częstotliwość aktualizacji">
            <input value={form.updateFrequency} onChange={(e) => setForm({ ...form, updateFrequency: e.target.value })} maxLength={40} />
          </Field>
          <Field label="Licencja / warunki wykorzystania">
            <input value={form.license} onChange={(e) => setForm({ ...form, license: e.target.value })} required maxLength={200} />
          </Field>
          <Field label="Uzasadnienie kwalifikacji" hint="Dlaczego to źródło jest wiarygodne i do czego będzie używane?">
            <textarea rows={3} value={form.qualification} onChange={(e) => setForm({ ...form, qualification: e.target.value })} required maxLength={500} />
          </Field>
        </form>
      </Modal>

      <Modal
        open={!!changing}
        onClose={() => setChanging(null)}
        title={changing?.status === 'excluded' ? 'Wyklucz źródło' : 'Zawieś źródło'}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setChanging(null)}>
              Anuluj
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !note.trim()}
              onClick={async () => {
                if (!changing) return;
                const ok = await run(async () => replace(await api.updateSource(changing.source.id, { status: changing.status, statusNote: note })), 'Zapisano.');
                if (ok) setChanging(null);
              }}
            >
              {changing?.status === 'excluded' ? 'Wyklucz' : 'Zawieś'}
            </button>
          </>
        }
      >
        <p>
          <strong>{changing?.source.name}</strong> ({changing?.source.domain})
        </p>
        <Field label="Uzasadnienie (wymagane, trafia do dziennika audytu)">
          <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
        </Field>
      </Modal>
    </>
  );
}
