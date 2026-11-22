import { type FormEvent, useState } from 'react';
import { getApi } from '../api/index.ts';
import type { TrustedSite, TrustedSiteInput } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { Async, Badge, Card, EmptyState, Field, Kpi, Modal, PageHeader, SearchInput, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtRelative } from '../utils/format.ts';

const EMPTY: TrustedSiteInput = { url: 'https://', name: '', topics: [], description: '' };

/** How the verification searches the site (`trustedSources` adapters). */
const ADAPTER: Record<string, string> = {
  govpl_search: 'Wyszukiwarka gov.pl',
  fact_check_publisher: 'Serwis fact-checkingowy',
  site_search: 'Wyszukiwarka strony',
  sitemap: 'Mapa strony',
  rss: 'Kanał RSS',
};

const TRUST: Record<string, string> = { official: 'Urzędowe', fact_checker: 'Fact-checking' };

type Filter = 'all' | 'enabled' | 'disabled' | 'problems';

const hasProblem = (s: TrustedSite) => s.enabled && (!s.loaded || s.lastCheck?.ok === false);

export default function TrustedSitesPage() {
  const api = getApi();
  const { can } = useAuth();
  const sites = useAsync(() => api.listTrustedSites(), []);
  const { run, busy } = useAction();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<TrustedSiteInput>(EMPTY);
  const [topics, setTopics] = useState('');
  const [removing, setRemoving] = useState<TrustedSite | null>(null);

  const all = sites.data ?? [];
  const enabled = all.filter((s) => s.enabled);
  const domains = new Set(enabled.map((s) => s.domain));
  const problems = all.filter(hasProblem);
  const query = search.trim().toLowerCase();
  const rows = all.filter(
    (s) =>
      (filter === 'all' ||
        (filter === 'enabled' && s.enabled) ||
        (filter === 'disabled' && !s.enabled) ||
        (filter === 'problems' && hasProblem(s))) &&
      (!query || `${s.name} ${s.domain} ${s.topics.join(' ')}`.toLowerCase().includes(query)),
  );
  const writable = can('sources:write');

  const replace = (updated: TrustedSite) =>
    sites.setData((list) => (list ?? []).map((s) => (s.url === updated.url ? updated : s)));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let created: TrustedSite | null = null;
    const input = {
      ...form,
      topics: topics
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    };
    const ok = await run(async () => {
      created = await api.createTrustedSite(input);
    }, 'Strona dodana. Weryfikacja przeszuka ją przy następnych sprawdzeniach.');
    if (ok && created) {
      sites.setData((list) => [...(list ?? []), created as TrustedSite]);
      setAdding(false);
      setForm(EMPTY);
      setTopics('');
    }
  };

  return (
    <>
      <PageHeader
        title="Strony zaufane"
        description="Strony, które przeszukuje weryfikacja (strona WWW i bot WhatsApp). Zmiany działają od razu, bez restartu serwisu, i trafiają do dziennika audytu. Ta sama lista jest publicznie dostępna pod /api/trusted-sources (tylko włączone strony)."
        actions={
          <>
            {can('export') && (
              <>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() =>
                    exportCsv('strony-zaufane', all, [
                      { header: 'nazwa', value: (s) => s.name },
                      { header: 'url', value: (s) => s.url },
                      { header: 'tematy', value: (s) => s.topics.join('; ') },
                      { header: 'włączona', value: (s) => (s.enabled ? 'tak' : 'nie') },
                      { header: 'wyszukiwanie', value: (s) => s.adapter ?? '' },
                      { header: 'ostatnie sprawdzenie', value: (s) => s.lastCheck?.at ?? '' },
                      { header: 'opis', value: (s) => s.description },
                    ])
                  }
                >
                  <Icon name="download" size={16} /> CSV
                </button>
                <button type="button" className="btn btn-sm" onClick={() => exportJson('strony-zaufane', all)}>
                  <Icon name="download" size={16} /> JSON
                </button>
              </>
            )}
            {writable && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => setAdding(true)}>
                <Icon name="plus" size={16} /> Dodaj stronę
              </button>
            )}
          </>
        }
      />

      <Async state={sites}>
        {() => (
          <>
            <div className="kpi-grid kpi-grid-4">
              <Kpi icon="database" label="Strony włączone" value={enabled.length} hint={`z ${all.length} na liście`} />
              <Kpi icon="external" label="Domeny" value={domains.size} hint="wśród włączonych stron" />
              <Kpi
                icon="search"
                label="Sposób wyszukiwania wykryty"
                value={enabled.filter((s) => s.adapter).length}
                hint="pozostałe zostaną wykryte przy pierwszym użyciu"
              />
              <Kpi
                icon="alert"
                label="Wymaga uwagi"
                value={problems.length}
                tone={problems.length ? 'warning' : undefined}
                hint="nieudane sprawdzenie albo strona jeszcze niewczytana"
              />
            </div>

            <div className="toolbar">
              <SearchInput value={search} onChange={setSearch} placeholder="Szukaj nazwy, domeny lub tematu…" />
              <label className="select-label">
                Pokaż
                <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
                  <option value="all">Wszystkie</option>
                  <option value="enabled">Włączone</option>
                  <option value="disabled">Wyłączone</option>
                  <option value="problems">Wymagające uwagi</option>
                </select>
              </label>
            </div>

            <Card padded={false}>
              {rows.length === 0 ? (
                <EmptyState title={all.length ? 'Brak stron dla filtrów' : 'Lista jest pusta'} icon="database">
                  {!all.length && 'Weryfikacja używa wtedy listy wbudowanej w kod (python -m database seed-sources ją wczyta).'}
                </EmptyState>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Strona</th>
                        <th>Tematy</th>
                        <th>Wyszukiwanie</th>
                        <th>Sprawdzenie</th>
                        <th>Status</th>
                        {writable && <th>Akcje</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((s) => (
                        <tr key={s.url}>
                          <td>
                            <strong>{s.name}</strong>
                            <div className="small">
                              <a href={s.url} target="_blank" rel="noopener noreferrer nofollow">
                                {s.domain} <Icon name="external" size={11} />
                              </a>
                              {s.trust && <span className="muted"> · {TRUST[s.trust] ?? s.trust}</span>}
                            </div>
                            {s.description && <div className="muted small">{s.description}</div>}
                          </td>
                          <td className="small">{s.topics.length ? s.topics.join(', ') : <span className="muted">—</span>}</td>
                          <td className="small">
                            {s.adapter ? ADAPTER[s.adapter] ?? s.adapter : <span className="muted">do wykrycia</span>}
                            {s.adapterLocked && <div className="muted">ustawione ręcznie</div>}
                          </td>
                          <td className="small nowrap">
                            {!s.loaded && s.enabled ? (
                              <Badge tone="warning" title="Serwis wczyta listę ponownie w ciągu kilku minut.">
                                Niewczytana
                              </Badge>
                            ) : s.lastCheck ? (
                              <>
                                {s.lastCheck.ok ? <Badge tone="good">OK</Badge> : <Badge tone="warning">Błąd</Badge>}
                                <div className="muted">{fmtRelative(s.lastCheck.at)}</div>
                                {s.lastCheck.error && <div className="muted">{s.lastCheck.error}</div>}
                              </>
                            ) : (
                              <span className="muted">—</span>
                            )}
                          </td>
                          <td>
                            {s.enabled ? <Badge tone="good">Włączona</Badge> : <Badge tone="muted">Wyłączona</Badge>}
                          </td>
                          {writable && (
                            <td>
                              <div className="row gap-xs wrap">
                                {s.enabled && s.loaded && (
                                  <button
                                    type="button"
                                    className="btn btn-xs"
                                    disabled={busy}
                                    title="Pobiera stronę i ponownie wykrywa, jak ją przeszukiwać"
                                    onClick={() => run(async () => replace(await api.checkTrustedSite(s.url)), 'Strona sprawdzona.')}
                                  >
                                    Sprawdź
                                  </button>
                                )}
                                <button
                                  type="button"
                                  className="btn btn-xs"
                                  disabled={busy}
                                  onClick={() =>
                                    run(
                                      async () => replace(await api.updateTrustedSite(s.url, { enabled: !s.enabled })),
                                      s.enabled ? 'Strona wyłączona.' : 'Strona włączona.',
                                    )
                                  }
                                >
                                  {s.enabled ? 'Wyłącz' : 'Włącz'}
                                </button>
                                <button type="button" className="btn btn-xs btn-ghost" disabled={busy} onClick={() => setRemoving(s)}>
                                  Usuń
                                </button>
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
          </>
        )}
      </Async>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="Dodaj stronę zaufaną"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              Anuluj
            </button>
            <button type="submit" form="site-form" className="btn btn-primary" disabled={busy}>
              Dodaj
            </button>
          </>
        }
      >
        <form id="site-form" className="form-grid" onSubmit={submit}>
          <Field label="Adres URL" hint="Cała strona albo jej dział, np. https://www.gov.pl/web/zdrowie">
            <input type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required maxLength={2000} />
          </Field>
          <Field label="Nazwa">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={200} />
          </Field>
          <Field label="Tematy" hint="Po przecinku, np. zdrowie, szczepienia">
            <input value={topics} onChange={(e) => setTopics(e.target.value)} maxLength={500} />
          </Field>
          <Field label="Opis" hint="Czym jest strona i dlaczego jest wiarygodna">
            <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={2000} />
          </Field>
        </form>
      </Modal>

      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title="Usuń stronę z listy"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setRemoving(null)}>
              Anuluj
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={async () => {
                if (!removing) return;
                const url = removing.url;
                const ok = await run(() => api.deleteTrustedSite(url), 'Strona usunięta z listy.');
                if (ok) {
                  sites.setData((list) => (list ?? []).filter((s) => s.url !== url));
                  setRemoving(null);
                }
              }}
            >
              Usuń
            </button>
          </>
        }
      >
        <p>
          <strong>{removing?.name}</strong> ({removing?.domain}) przestanie być przeszukiwana. Jeśli chcesz ją tylko
          czasowo pominąć, użyj „Wyłącz”.
        </p>
      </Modal>
    </>
  );
}
