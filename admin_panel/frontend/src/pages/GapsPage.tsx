import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { QueryCluster } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Sparkline } from '../components/charts.tsx';
import { ClusterDrawer } from '../components/ClusterDrawer.tsx';
import { Icon } from '../components/icons.tsx';
import { channelLabel, GAP_STATUS } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, Kpi, PageHeader, SearchInput } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtPct, fmtRelative, plural } from '../utils/format.ts';

export default function GapsPage() {
  const api = getApi();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [picked, setPicked] = useState<QueryCluster | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const lifecycle = supports('gapLifecycle');
  const withCases = supports('cases');
  const clusters = useAsync(() => api.listClusters(showClosed ? {} : { onlyGaps: true }), [showClosed]);
  const rules = useAsync(() => (supports('alertRules') ? api.getAlertRules() : Promise.resolve(null)), []);
  const runtime = useAsync(
    () => (supports('runtimeConfig') && can('settings:read') ? api.getRuntimeConfig() : Promise.resolve(null)),
    [],
  );

  // `?focus=<id>` (from an alert) opens that topic; it may be closed, so it is loaded on its own.
  const focusId = params.get('focus');
  const focused = useAsync<QueryCluster | null>(
    () => (focusId ? api.getCluster(focusId) : Promise.resolve(null)),
    [focusId],
  );
  const selected = picked ?? focused.data ?? null;
  const closeDrawer = () => {
    setPicked(null);
    if (focusId) {
      params.delete('focus');
      setParams(params, { replace: true });
    }
  };
  const onChanged = (cluster: QueryCluster) => {
    setPicked(cluster);
    clusters.reload();
  };

  const filtered = (clusters.data ?? []).filter(
    (c) => !search.trim() || c.label.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const isClosed = (c: QueryCluster) => c.gapStatus === 'closed' || c.gapStatus === 'rejected';
  const gaps = filtered.filter((c) => c.isInformationGap);
  const watch = filtered.filter((c) => !c.isInformationGap && !isClosed(c));
  const closed = filtered.filter(isClosed);
  const waiting = lifecycle ? gaps.filter((c) => c.gapStatus === 'active') : gaps.filter((c) => !c.caseId);

  const exportRows = (format: 'csv' | 'json') => {
    if (format === 'json') return exportJson('luki-informacyjne', filtered);
    exportCsv('luki-informacyjne', filtered, [
      { header: 'temat', value: (c) => c.label },
      { header: 'luka', value: (c) => (c.isInformationGap ? 'tak' : 'obserwowane') },
      { header: 'bez dowodów', value: (c) => c.noEvidence },
      { header: 'odsetek bez dowodów', value: (c) => c.noEvidenceRatio.toFixed(2) },
      { header: 'zapytania łącznie', value: (c) => c.total },
      { header: 'tematy ryzyka', value: (c) => c.riskTopics.join(', ') },
      { header: 'czego brakuje', value: (c) => c.missing ?? '' },
      { header: 'ostatnie zapytanie', value: (c) => c.lastSeen },
      { header: 'sprawa', value: (c) => c.caseId ?? '' },
      { header: 'stan luki', value: (c) => (c.gapStatus ? GAP_STATUS[c.gapStatus].label : '') },
      { header: 'notatka', value: (c) => c.gapNote ?? '' },
    ]);
  };

  const g = rules.data?.informationGap;
  const m = runtime.data?.monitoring;

  return (
    <>
      <PageHeader
        title="Luki informacyjne"
        description="Tematy, o które obywatele pytają wielokrotnie, a system nie znajduje wiarygodnych źródeł i wstrzymuje się od rozstrzygnięcia. To sygnał dla analityka: brakuje komunikatu lub źródła w katalogu."
        actions={
          can('export') ? (
            <>
              <button type="button" className="btn btn-sm" onClick={() => exportRows('csv')}>
                <Icon name="download" size={16} /> CSV
              </button>
              <button type="button" className="btn btn-sm" onClick={() => exportRows('json')}>
                <Icon name="download" size={16} /> JSON
              </button>
            </>
          ) : undefined
        }
      />

      {g && (
        <div className="rule-strip">
          <Icon name="sliders" size={16} />
          <span>
            Luka = co najmniej <strong>{g.minQueries}</strong> podobnych zapytań w ciągu <strong>{g.windowHours} h</strong>, z
            których <strong>≥ {fmtPct(g.minNoEvidenceRatio)}</strong> zakończyło się brakiem dowodów (próg podobieństwa{' '}
            {g.similarityThreshold}).
          </span>
          {can('rules:read') && (
            <Link to="/rules" className="btn btn-sm btn-ghost">
              Zmień reguły
            </Link>
          )}
        </div>
      )}
      {m && (
        <div className="rule-strip">
          <Icon name="sliders" size={16} />
          <span>
            Luka = co najmniej <strong>{m.info_gap_min_queries}</strong>{' '}
            {plural(m.info_gap_min_queries, ['zapytanie', 'zapytania', 'zapytań'])} w ciągu{' '}
            <strong>{m.info_gap_window_hours} h</strong> o temat, którego system nie rozstrzygnął (brak źródeł albo
            niewystarczające dane). Pierwsze rozstrzygnięcie oparte na źródłach zamyka lukę automatycznie.
          </span>
          {can('settings:read') && (
            <Link to="/thresholds" className="btn btn-sm btn-ghost">
              Zmień progi
            </Link>
          )}
        </div>
      )}

      <Async state={clusters}>
        {() => (
          <>
            <div className="kpi-grid kpi-grid-3">
              <Kpi
                icon="gap"
                label="Aktywne luki"
                value={gaps.length}
                tone={gaps.some((c) => c.riskTopics.length) || (lifecycle && gaps.length > 0) ? 'critical' : undefined}
                hint={
                  lifecycle
                    ? `${gaps.filter((c) => c.gapStatus === 'in_progress').length} w uzupełnianiu`
                    : `${gaps.filter((c) => c.riskTopics.length).length} w tematach wysokiego ryzyka`
                }
              />
              <Kpi icon="history" label="Zapytania bez dowodów" value={gaps.reduce((s, c) => s + c.noEvidence, 0)} hint="w grupach uznanych za luki" />
              <Kpi
                icon="folder"
                label={lifecycle ? 'Czekają na decyzję' : 'Luki bez sprawy'}
                value={waiting.length}
                hint={lifecycle ? 'nikt jeszcze nie uzupełnia źródeł' : 'wymagają decyzji'}
              />
            </div>

            <div className="toolbar">
              <SearchInput value={search} onChange={setSearch} placeholder="Szukaj tematu…" />
              {lifecycle && (
                <label className="check-row">
                  <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Pokaż
                  zamknięte i odrzucone
                </label>
              )}
            </div>

            <Card
              title="Luki informacyjne"
              subtitle={
                withCases
                  ? 'Spełniają próg reguły — utwórz sprawę albo przekaż analitykowi.'
                  : 'Spełniają próg reguły. Oznacz „w uzupełnianiu”, gdy ktoś przygotowuje komunikat lub źródło, a potem zamknij.'
              }
              padded={false}
            >
              {gaps.length === 0 ? (
                <EmptyState title="Brak luk informacyjnych" icon="check">
                  Żadna grupa zapytań nie przekracza progu reguły.
                </EmptyState>
              ) : (
                <GapTable rows={gaps} onOpen={setPicked} withCases={withCases} />
              )}
            </Card>

            {watch.length > 0 && (
              <Card
                title="Obserwowane"
                subtitle={
                  lifecycle
                    ? 'Pytania bez rozstrzygnięcia, ale za mało zapytań, by uznać temat za lukę.'
                    : 'Wysoki odsetek braku dowodów, ale za mało zapytań, by uznać to za lukę.'
                }
                padded={false}
              >
                <GapTable rows={watch} onOpen={setPicked} withCases={withCases} />
              </Card>
            )}

            {showClosed && closed.length > 0 && (
              <Card title="Zamknięte i odrzucone" subtitle="Można je otworzyć ponownie z widoku szczegółów." padded={false}>
                <GapTable rows={closed} onOpen={setPicked} withCases={withCases} />
              </Card>
            )}
          </>
        )}
      </Async>

      <ClusterDrawer cluster={selected} onClose={closeDrawer} onChanged={onChanged} />
    </>
  );
}

function GapTable({ rows, onOpen, withCases }: { rows: QueryCluster[]; onOpen: (c: QueryCluster) => void; withCases: boolean }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Temat</th>
            <th className="num">Bez dowodów</th>
            <th>Trend 48 h</th>
            <th>{withCases ? 'Kanały' : 'Zapytania'}</th>
            <th>Ostatnie</th>
            <th>{withCases ? 'Sprawa' : 'Stan'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => onOpen(c)}>
              <td>
                <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); onOpen(c); }}>
                  {c.label}
                </button>
                <div className="row gap-xs wrap">
                  {c.riskTopics.map((r) => (
                    <Badge key={r} tone="critical">
                      {r}
                    </Badge>
                  ))}
                </div>
              </td>
              <td className="num">
                <strong>{c.noEvidence}</strong> {plural(c.noEvidence, ['zapytanie', 'zapytania', 'zapytań'])}
                <div className="muted small">{fmtPct(c.noEvidenceRatio)} w oknie</div>
              </td>
              <td>
                <Sparkline values={c.hourly} label={`Trend zapytań: ${c.label}`} />
              </td>
              <td className="small">
                {withCases
                  ? Object.entries(c.channels)
                      .map(([k, v]) => `${channelLabel(k)} ${v}`)
                      .join(' · ')
                  : `${c.uniqueSessions} ${plural(c.uniqueSessions, ['zapytanie', 'zapytania', 'zapytań'])}`}
              </td>
              <td className="small nowrap">{fmtRelative(c.lastSeen)}</td>
              <td>
                {c.gapStatus && !withCases ? (
                  <Badge tone={GAP_STATUS[c.gapStatus].tone}>{GAP_STATUS[c.gapStatus].label}</Badge>
                ) : c.caseId ? (
                  <Link to={`/cases/${c.caseId}`} onClick={(e) => e.stopPropagation()}>
                    {c.caseId}
                  </Link>
                ) : (
                  <Badge tone="warning">Brak — rekomendacja</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
