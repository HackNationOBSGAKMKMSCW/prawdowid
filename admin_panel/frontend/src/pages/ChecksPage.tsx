import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { CheckFlag, CheckOutcome, CheckQuery, CheckRecord, Verdict } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon } from '../components/icons.tsx';
import { channelLabel, FLAG, INPUT_KIND, OUTCOME, PIPELINE_ROLE, REPORT_REASON, STRENGTH, VERDICT } from '../components/labels.ts';
import { Async, Badge, Card, Drawer, EmptyState, Modal, PageHeader, Pagination, SearchInput, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtDate, fmtDateTime, fmtDuration, fmtPln, truncate } from '../utils/format.ts';

function ResultBadge({ check }: { check: CheckRecord }) {
  if (check.overallVerdict) {
    const v = VERDICT[check.overallVerdict];
    return <Badge tone={v.tone}>{v.label}</Badge>;
  }
  const o = OUTCOME[check.outcome];
  return <Badge tone={o.tone}>{o.label}</Badge>;
}

/** Sources found: the backend may report only a count, the mock lists the materials. */
function sourceCount(check: CheckRecord): number | null {
  if (check.sourcesCount !== undefined && check.sourcesCount !== null) return check.sourcesCount;
  if (check.claims.some((c) => c.sourcesCount !== undefined && c.sourcesCount !== null)) {
    return check.claims.reduce((s, c) => s + (c.sourcesCount ?? 0), 0);
  }
  if (check.outcome === 'refused' || check.outcome === 'pending') return null;
  return check.claims.reduce((s, cl) => s + cl.evidence.length, 0);
}

export default function ChecksPage() {
  const api = getApi();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const clusterId = params.get('cluster') ?? undefined;
  const [search, setSearch] = useState(params.get('q') ?? '');
  const [filters, setFilters] = useState<CheckQuery>({ outcome: 'any', verdict: 'any', channel: 'any', flag: 'any', sinceHours: 168 });
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState<string | null>(null);
  const selectedId = picked ?? params.get('focus');
  const [confirmDelete, setConfirmDelete] = useState<CheckRecord | null>(null);
  const { run, busy } = useAction();
  const { checkFlags, checkOutcomes } = api.capabilities;
  const showCost = supports('checkCost');
  const showUser = supports('endUsers');

  const query: CheckQuery = { ...filters, search, clusterId, page, pageSize: 25 };
  const checks = useAsync(() => api.listChecks(query), [JSON.stringify(query)]);
  // The list may omit claims and sources; the drawer always loads the full record.
  const selected = useAsync<CheckRecord | null>(() => (selectedId ? api.getCheck(selectedId) : Promise.resolve(null)), [selectedId]);

  const closeDetail = () => {
    setPicked(null);
    if (params.has('focus')) {
      params.delete('focus');
      setParams(params, { replace: true });
    }
  };

  const update = (patch: Partial<CheckQuery>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const exportAll = async (format: 'csv' | 'json') => {
    await run(async () => {
      const all = await api.listChecks({ ...query, page: 1, pageSize: 5000 });
      if (format === 'json') return exportJson('historia-weryfikacji', all.items);
      exportCsv('historia-weryfikacji', all.items, [
        { header: 'id', value: (c) => c.id },
        { header: 'czas', value: (c) => c.createdAt },
        { header: 'kanał', value: (c) => c.channel },
        { header: 'typ wejścia', value: (c) => c.inputKind },
        { header: 'zapytanie (zamaskowane)', value: (c) => c.query },
        { header: 'wynik', value: (c) => (c.overallVerdict ? VERDICT[c.overallVerdict].label : OUTCOME[c.outcome].label) },
        { header: 'siła podstaw', value: (c) => STRENGTH[c.strength] },
        { header: 'źródła', value: (c) => c.claims.flatMap((cl) => cl.evidence.map((e) => e.url)).join(' ') },
        { header: 'czas odpowiedzi ms', value: (c) => c.durationMs },
        { header: 'koszt zł', value: (c) => c.costPln },
        { header: 'flagi', value: (c) => c.flags.join(',') },
      ]);
    }, 'Wyeksportowano.');
  };

  return (
    <>
      <PageHeader
        title="Historia weryfikacji"
        description="Zapis przebiegu każdego sprawdzenia: pytanie (z zamaskowanymi danymi osobowymi), czas, użyte źródła, wynik, modele i koszt."
        actions={
          can('export') ? (
            <>
              <button type="button" className="btn btn-sm" disabled={busy} onClick={() => exportAll('csv')}>
                <Icon name="download" size={16} /> CSV
              </button>
              <button type="button" className="btn btn-sm" disabled={busy} onClick={() => exportAll('json')}>
                <Icon name="download" size={16} /> JSON
              </button>
            </>
          ) : undefined
        }
      />

      {clusterId && (
        <div className="rule-strip">
          <Icon name="repeat" size={16} />
          <span>
            Filtr: zapytania z jednej grupy podobnych pytań.
            {!supports('cases') && ' Pozostałe filtry nie są wtedy stosowane.'}
          </span>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              params.delete('cluster');
              setParams(params);
              setPage(1);
            }}
          >
            Wyczyść filtr
          </button>
        </div>
      )}

      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          placeholder="Szukaj w treści zapytania lub ID…"
        />
        <label className="select-label">
          Wynik
          <select
            value={filters.verdict !== 'any' ? `v:${filters.verdict}` : filters.outcome !== 'any' ? `o:${filters.outcome}` : 'any'}
            onChange={(e) => {
              const [kind, val] = e.target.value.split(':');
              if (kind === 'v') update({ verdict: val as Verdict, outcome: 'any' });
              else if (kind === 'o') update({ outcome: val as CheckOutcome, verdict: 'any' });
              else update({ verdict: 'any', outcome: 'any' });
            }}
          >
            <option value="any">Wszystkie</option>
            {Object.entries(VERDICT).map(([k, v]) => (
              <option key={k} value={`v:${k}`}>
                {v.label}
              </option>
            ))}
            {checkOutcomes.map((o) => (
              <option key={o} value={`o:${o}`}>
                {OUTCOME[o].label}
              </option>
            ))}
          </select>
        </label>
        {supports('channelFilter') && (
          <label className="select-label">
            Kanał
            <select value={filters.channel} onChange={(e) => update({ channel: e.target.value })}>
              <option value="any">Wszystkie</option>
              <option value="web">WWW</option>
              <option value="whatsapp">WhatsApp</option>
            </select>
          </label>
        )}
        <label className="select-label">
          Flaga
          <select value={filters.flag} onChange={(e) => update({ flag: e.target.value as CheckFlag | 'any' })}>
            <option value="any">Dowolna</option>
            {checkFlags.map((k) => (
              <option key={k} value={k}>
                {FLAG[k].label}
              </option>
            ))}
          </select>
        </label>
        <label className="select-label">
          Okres
          <select value={filters.sinceHours} onChange={(e) => update({ sinceHours: Number(e.target.value) })}>
            <option value={6}>6 h</option>
            <option value={24}>24 h</option>
            <option value={168}>7 dni</option>
            <option value={720}>30 dni</option>
          </select>
        </label>
      </div>

      <Card padded={false}>
        <Async state={checks}>
          {(result) =>
            result.items.length === 0 ? (
              <EmptyState title="Brak zapisów dla wybranych filtrów" icon="history" />
            ) : (
              <>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Czas</th>
                        <th>Kanał</th>
                        {showUser && <th>Użytkownik</th>}
                        <th className="col-wide">Zapytanie</th>
                        <th>Wynik</th>
                        {showCost && <th>Siła</th>}
                        <th className="num">Źródła</th>
                        <th className="num">Czas odp.</th>
                        {showCost && <th className="num">Koszt</th>}
                        <th>Flagi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.items.map((c) => (
                        <tr key={c.id} className="clickable" onClick={() => setPicked(c.id)}>
                          <td className="nowrap small">{fmtDateTime(c.createdAt)}</td>
                          <td className="small">{channelLabel(c.channel)}</td>
                          {showUser && (
                            <td className="small mono">
                              {c.userKey ? (
                                <Link to={`/end-users?focus=${encodeURIComponent(c.userKey)}`} onClick={(e) => e.stopPropagation()}>
                                  {c.userLabel ?? c.userKey}
                                </Link>
                              ) : (
                                '—'
                              )}
                            </td>
                          )}
                          <td>
                            <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); setPicked(c.id); }}>
                              {truncate(c.query, 80)}
                            </button>
                          </td>
                          <td>
                            <ResultBadge check={c} />
                          </td>
                          {showCost && <td className="small">{STRENGTH[c.strength]}</td>}
                          <td className="num">{sourceCount(c) ?? '—'}</td>
                          <td className="num nowrap">{fmtDuration(c.durationMs)}</td>
                          {showCost && <td className="num nowrap">{fmtPln(c.costPln, 3)}</td>}
                          <td>
                            <div className="row gap-xs wrap">
                              {c.flags.map((f) => (
                                <Badge key={f} tone={FLAG[f].tone}>
                                  {FLAG[f].label}
                                </Badge>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={result.page} pageSize={result.pageSize} total={result.total} onPage={setPage} />
              </>
            )
          }
        </Async>
      </Card>

      <Drawer
        open={!!selectedId}
        onClose={closeDetail}
        wide
        title="Przebieg sprawdzenia"
        footer={
          selected.data && (
            <>
              <button type="button" className="btn" onClick={() => selected.data && exportJson(`sprawdzenie-${selected.data.id}`, selected.data)}>
                <Icon name="download" size={16} /> JSON
              </button>
              {can('checks:delete') && supports('deleteCheck') && (
                <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(selected.data ?? null)}>
                  <Icon name="trash" size={16} /> Usuń zapis
                </button>
              )}
            </>
          )
        }
      >
        <Async state={selected}>{(check) => (check ? <CheckDetail check={check} /> : null)}</Async>
      </Drawer>

      <Modal
        open={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        title="Usunąć zapis sprawdzenia?"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setConfirmDelete(null)}>
              Anuluj
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={async () => {
                if (!confirmDelete) return;
                const ok = await run(() => api.deleteCheck(confirmDelete.id), 'Zapis usunięty.');
                if (ok) {
                  setConfirmDelete(null);
                  closeDetail();
                  checks.reload();
                }
              }}
            >
              Usuń trwale
            </button>
          </>
        }
      >
        <p>
          Zapis <code>{confirmDelete?.id}</code> zostanie trwale usunięty (np. na żądanie użytkownika). Operacja trafi
          do dziennika audytu.
        </p>
      </Modal>
    </>
  );
}

function CheckDetail({ check }: { check: CheckRecord }) {
  return (
    <div className="stack">
      <div className="row gap-sm wrap">
        <ResultBadge check={check} />
        <Badge tone="muted">{channelLabel(check.channel)}</Badge>
        <Badge tone="muted">{INPUT_KIND[check.inputKind]}</Badge>
        {check.flags.map((f) => (
          <Badge key={f} tone={FLAG[f].tone}>
            {FLAG[f].label}
          </Badge>
        ))}
      </div>

      <div>
        <div className="field-label">Zapytanie (dane osobowe zamaskowane)</div>
        <blockquote className="query-quote">{check.query}</blockquote>
      </div>

      {check.flags.includes('prompt_injection') && (
        <div className="notice notice-critical">
          <Icon name="shield" size={16} />
          <div>
            Wykryto próbę zmiany zasad działania (prompt injection). Instrukcje z treści potraktowano jako dane i
            zignorowano; zdarzenie zapisano w dzienniku bezpieczeństwa.
          </div>
        </div>
      )}
      {check.flags.includes('source_status_warning') && (
        <div className="notice notice-warning">
          <Icon name="info" size={16} />
          <div>
            Neutralne ostrzeżenie o statusie źródła (podmiot objęty sankcjami UE) zostało pokazane użytkownikowi
            osobno. Status źródła nie był podstawą werdyktu.
          </div>
        </div>
      )}
      {check.outcome === 'technical_error' && (
        <div className="notice notice-warning">
          <Icon name="alert" size={16} />
          <div>
            <strong>Awaria techniczna — to nie jest werdykt.</strong> {check.errorMessage}
          </div>
        </div>
      )}
      {check.outcome === 'refused' && (
        <div className="notice notice-critical">
          <Icon name="lock" size={16} />
          <div>
            <strong>Zapytanie odrzucone — nie zostało sprawdzone.</strong> {check.errorMessage}
          </div>
        </div>
      )}
      {check.report && (
        <div className="notice notice-warning">
          <Icon name="alert" size={16} />
          <div>
            <strong>Zgłoszony błąd: {REPORT_REASON[check.report.reason] ?? check.report.reason}.</strong>{' '}
            {check.report.comment ? `„${check.report.comment}”` : 'Bez komentarza.'}
            {check.report.at && <span className="muted"> · {fmtDateTime(check.report.at)}</span>}
          </div>
        </div>
      )}
      {check.outcome === 'pending' && (
        <div className="notice notice-info">
          <Icon name="refresh" size={16} />
          <div>Sprawdzanie jeszcze trwa albo zostało przerwane przed zapisaniem wyniku.</div>
        </div>
      )}
      {check.riskTopics.length > 0 && (
        <div className="notice notice-warning">
          <Icon name="alert" size={16} />
          <div>
            <strong>Treści niebezpieczne:</strong> {check.riskTopics.join(', ')}. Zapytanie zostało oznaczone do
            obserwacji.
          </div>
        </div>
      )}
      {check.outcome === 'needs_clarification' && (
        <div className="notice notice-info">
          <Icon name="info" size={16} />
          <div>Pytanie nie zawierało twierdzenia do sprawdzenia — użytkownik został poproszony o doprecyzowanie.</div>
        </div>
      )}

      {check.claims.map((claim, i) => (
        <section key={claim.id} className="claim">
          <div className="claim-head">
            <span className="muted small">Twierdzenie {i + 1}</span>
            {claim.verdict ? (
              <Badge tone={VERDICT[claim.verdict].tone}>{VERDICT[claim.verdict].label}</Badge>
            ) : (
              <Badge tone="warning">Brak werdyktu</Badge>
            )}
            {claim.strength !== 'unknown' && <span className="muted small">Siła podstaw: {STRENGTH[claim.strength]}</span>}
          </div>
          <p className="claim-text">„{claim.text}”</p>
          {claim.rationale && (
            <>
              <div className="field-label">Uzasadnienie (interpretacja modelu)</div>
              <p>{claim.rationale}</p>
            </>
          )}
          {claim.missing && (
            <div className="notice notice-warning">
              <Icon name="gap" size={16} />
              <div>
                <strong>Czego nie udało się ustalić:</strong> {claim.missing}
              </div>
            </div>
          )}
          <div className="field-label">Materiały źródłowe ({claim.evidence.length || (claim.sourcesCount ?? 0)})</div>
          {claim.evidence.length === 0 ? (
            <p className="muted small">
              {claim.sourcesCount
                ? `Znaleziono źródeł: ${claim.sourcesCount}. Backend zapisuje tylko ich liczbę — szczegóły są w logach technicznych żądania.`
                : 'Nie znaleziono materiałów w źródłach danych.'}
            </p>
          ) : (
            <ul className="evidence">
              {claim.evidence.map((e) => (
                <li key={e.id}>
                  <div className="row gap-sm wrap">
                    <Badge tone={e.stance === 'supports' ? 'good' : e.stance === 'refutes' ? 'critical' : 'neutral'}>
                      {e.stance === 'supports' ? 'Potwierdza' : e.stance === 'refutes' ? 'Obala' : 'Kontekst'}
                    </Badge>
                    <a href={e.url} target="_blank" rel="noopener noreferrer nofollow">
                      {e.title} <Icon name="external" size={12} />
                    </a>
                  </div>
                  <div className="muted small">
                    {e.publisher} · publikacja: {fmtDate(e.publishedAt)} · pobrano: {fmtDateTime(e.retrievedAt)}
                  </div>
                  {e.snippet && <blockquote className="snippet">{e.snippet}</blockquote>}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      <section>
        <div className="field-label">Dane techniczne</div>
        <dl className="metrics">
          <div>
            <dt>ID</dt>
            <dd className="mono small">{check.id}</dd>
          </div>
          <div>
            <dt>Czas</dt>
            <dd>{fmtDateTime(check.createdAt)}</dd>
          </div>
          <div>
            <dt>Czas odpowiedzi</dt>
            <dd>{fmtDuration(check.durationMs)}</dd>
          </div>
          {check.userKey && (
            <div>
              <dt>Użytkownik</dt>
              <dd>
                <Link to={`/end-users?focus=${encodeURIComponent(check.userKey)}`}>{check.userLabel ?? check.userKey}</Link>
              </dd>
            </div>
          )}
          {check.requestId && (
            <div>
              <dt>Request ID</dt>
              <dd className="mono small">{check.requestId}</dd>
            </div>
          )}
          {supports('checkCost') && (
            <>
              <div>
                <dt>Tokeny</dt>
                <dd>{check.tokens}</dd>
              </div>
              <div>
                <dt>Koszt (szac.)</dt>
                <dd>{fmtPln(check.costPln, 4)}</dd>
              </div>
            </>
          )}
        </dl>
        {Object.keys(check.models).length > 0 && (
          <table className="table table-compact">
            <tbody>
              {Object.entries(check.models).map(([role, model]) => (
                <tr key={role}>
                  <td className="small">{PIPELINE_ROLE[role as keyof typeof PIPELINE_ROLE]?.label ?? role}</td>
                  <td className="mono small">{model}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {check.requestId && supports('techEvents') && (
          <Link to={`/logs?request=${encodeURIComponent(check.requestId)}`} className="btn btn-sm">
            <Icon name="search" size={14} /> Logi techniczne tego żądania
          </Link>
        )}
      </section>
    </div>
  );
}
