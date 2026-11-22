import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { TechEvent, TechEventQuery, TechSummary } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { BarList } from '../components/charts.tsx';
import { Icon } from '../components/icons.tsx';
import type { Tone } from '../components/labels.ts';
import { Async, Badge, Card, Drawer, EmptyState, Kpi, PageHeader, Tabs } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportJson } from '../utils/export.ts';
import { fmtDateTime, fmtDuration, fmtInt, truncate } from '../utils/format.ts';

const RANGES = [
  { value: '1', label: '1 h' },
  { value: '24', label: '24 h' },
  { value: '168', label: '7 dni' },
] as const;

const LEVEL_TONE: Record<string, Tone> = {
  debug: 'muted',
  info: 'neutral',
  warning: 'warning',
  error: 'critical',
  critical: 'critical',
};

const fmtMs = (ms: number | null | undefined) => (ms === null || ms === undefined ? '—' : fmtDuration(ms));

function fieldsPreview(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .filter(([k]) => k !== 'logger')
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' ');
}

export default function TechLogsPage() {
  const api = getApi();
  const { can } = useAuth();
  const [params] = useSearchParams();
  const fromCheck = params.get('request') ?? '';
  // Opened from a check: look further back, the request may be older than a day.
  const [range, setRange] = useState<(typeof RANGES)[number]['value']>(fromCheck ? '168' : '24');
  const [filters, setFilters] = useState<TechEventQuery>({ level: undefined, event: '', requestId: fromCheck, limit: 200 });
  const [selected, setSelected] = useState<TechEvent | null>(null);
  const hours = Number(range);
  const summary = useAsync(() => api.getTechSummary(hours), [hours]);
  const events = useAsync(() => api.listTechEvents({ ...filters, sinceHours: hours }), [hours, JSON.stringify(filters)]);

  return (
    <>
      <PageHeader
        title="Logi techniczne"
        description="Zdarzenia z modułu observability backendu: żądania, wywołania modeli i wyszukiwarek, błędy, próby prompt injection. Bez treści wiadomości — tylko metadane."
        actions={
          <>
            <Tabs label="Zakres czasu" value={range} onChange={setRange} options={[...RANGES]} />
            <button type="button" className="btn btn-sm" onClick={() => { summary.reload(); events.reload(); }}>
              <Icon name="refresh" size={14} /> Odśwież
            </button>
          </>
        }
      />

      <Async state={summary}>{(s) => <SummaryView summary={s} />}</Async>

      <div className="toolbar">
        <label className="select-label">
          Poziom
          <select value={filters.level ?? ''} onChange={(e) => setFilters({ ...filters, level: e.target.value || undefined })}>
            <option value="">Każdy</option>
            <option value="debug">debug</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
            <option value="critical">critical</option>
          </select>
        </label>
        <label className="select-label">
          Zdarzenie
          <input type="text" value={filters.event} placeholder="np. llm_call" onChange={(e) => setFilters({ ...filters, event: e.target.value })} />
        </label>
        <label className="select-label">
          Request ID
          <input type="text" value={filters.requestId} placeholder="identyfikator żądania" onChange={(e) => setFilters({ ...filters, requestId: e.target.value })} />
        </label>
        <label className="select-label">
          Limit
          <select value={filters.limit} onChange={(e) => setFilters({ ...filters, limit: Number(e.target.value) })}>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={2000}>2000</option>
          </select>
        </label>
      </div>

      <Card
        title="Zdarzenia"
        subtitle={events.data ? `Najnowsze na górze · plik ${events.data.file}` : undefined}
        padded={false}
        actions={
          can('export') &&
          events.data && (
            <button type="button" className="btn btn-sm" onClick={() => exportJson('logi-techniczne', events.data?.items ?? [])}>
              <Icon name="download" size={14} /> JSON
            </button>
          )
        }
      >
        <Async state={events}>
          {({ items }) =>
            items.length === 0 ? (
              <EmptyState title="Brak zdarzeń dla wybranych filtrów" icon="inbox">
                Backend zapisuje logi do pliku <code>LOG_FILE</code> (domyślnie <code>backend/logs/app.jsonl</code>), gdy
                działa z włączonym observability.
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead>
                    <tr>
                      <th>Czas</th>
                      <th>Poziom</th>
                      <th>Zdarzenie</th>
                      <th>Request ID</th>
                      <th>Szczegóły</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((e) => (
                      <tr key={e.id} className="clickable" onClick={() => setSelected(e)}>
                        <td className="small nowrap">{fmtDateTime(e.at)}</td>
                        <td>
                          <Badge tone={LEVEL_TONE[e.level] ?? 'neutral'}>{e.level}</Badge>
                        </td>
                        <td className="mono small">{e.event}</td>
                        <td className="mono small">{e.requestId ? truncate(e.requestId, 14) : '—'}</td>
                        <td className="cell-fields muted">{truncate(fieldsPreview(e.fields), 160)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
      </Card>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? selected.event : ''}
        footer={
          selected?.requestId && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                setFilters({ ...filters, requestId: selected.requestId, event: '' });
                setSelected(null);
              }}
            >
              <Icon name="search" size={16} /> Całe żądanie
            </button>
          )
        }
      >
        {selected && (
          <div className="stack">
            <div className="row gap-sm wrap">
              <Badge tone={LEVEL_TONE[selected.level] ?? 'neutral'}>{selected.level}</Badge>
              <span className="muted small">{fmtDateTime(selected.at)}</span>
            </div>
            <pre className="json-block">
              {JSON.stringify({ ts: selected.at, level: selected.level, event: selected.event, request_id: selected.requestId, ...selected.fields }, null, 2)}
            </pre>
          </div>
        )}
      </Drawer>
    </>
  );
}

function SummaryView({ summary: s }: { summary: TechSummary }) {
  const models = Object.entries(s.llm.by_model);
  const searchErrors = Object.entries(s.search.errors);
  const injections = Object.entries(s.prompt_injection.by_kind);
  return (
    <>
      <div className="kpi-grid">
        <Kpi icon="history" label="Żądania" value={fmtInt(s.requests.count)} hint={`${s.requests.failed} nieudanych · ${s.requests.abstained} bez werdyktu`} />
        <Kpi icon="refresh" label="Czas żądania (mediana)" value={fmtMs(s.requests.duration_ms_p50)} hint={`najwolniejsze 5%: ${fmtMs(s.requests.duration_ms_p95)}`} />
        <Kpi
          icon="alert"
          label="Linie z błędem"
          value={fmtInt(s.error_lines)}
          tone={s.error_lines ? 'warning' : undefined}
          hint={`wyszukiwanie: ${s.search.calls} wywołań`}
        />
      </div>

      <div className="grid-2">
        <Card title="Modele językowe" subtitle={`Opóźnienie: mediana ${fmtMs(s.llm.latency_ms_p50)}, 95%: ${fmtMs(s.llm.latency_ms_p95)}`} padded={false}>
          {models.length === 0 ? (
            <p className="card-body muted">Brak wywołań modeli w tym okresie.</p>
          ) : (
            <div className="table-wrap">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th className="num">Wywołania</th>
                    <th className="num">Błędy</th>
                    <th className="num">Tokeny (we/wy)</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map(([name, m]) => (
                    <tr key={name}>
                      <td className="mono small">{name}</td>
                      <td className="num">{m.calls}</td>
                      <td className="num">{m.errors}</td>
                      <td className="num small">
                        {fmtInt(m.prompt_tokens)} / {fmtInt(m.completion_tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Problemy">
          <h3 className="subhead">Błędy wyszukiwania</h3>
          {searchErrors.length === 0 ? (
            <p className="muted small">Brak.</p>
          ) : (
            <BarList items={searchErrors.map(([k, v]) => ({ key: k, label: k, value: v }))} />
          )}
          <h3 className="subhead">Próby prompt injection</h3>
          {injections.length === 0 ? (
            <p className="muted small">Brak.</p>
          ) : (
            <BarList items={injections.map(([k, v]) => ({ key: k, label: k, value: v }))} />
          )}
          {Object.keys(s.abstain).length > 0 && (
            <>
              <h3 className="subhead">Powody braku werdyktu</h3>
              <BarList items={Object.entries(s.abstain).map(([k, v]) => ({ key: k, label: k, value: v }))} />
            </>
          )}
        </Card>
      </div>
    </>
  );
}
