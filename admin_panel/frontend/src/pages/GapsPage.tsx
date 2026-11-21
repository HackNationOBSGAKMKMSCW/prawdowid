import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { QueryCluster } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Sparkline } from '../components/charts.tsx';
import { ClusterDrawer } from '../components/ClusterDrawer.tsx';
import { Icon } from '../components/icons.tsx';
import { channelLabel } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, Kpi, PageHeader, SearchInput } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv, exportJson } from '../utils/export.ts';
import { fmtPct, fmtRelative, plural } from '../utils/format.ts';

export default function GapsPage() {
  const api = getApi();
  const { can } = useAuth();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<QueryCluster | null>(null);
  const clusters = useAsync(() => api.listClusters({ onlyGaps: true }), []);
  const rules = useAsync(() => api.getAlertRules(), []);

  const filtered = (clusters.data ?? []).filter(
    (c) => !search.trim() || c.label.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const gaps = filtered.filter((c) => c.isInformationGap);
  const watch = filtered.filter((c) => !c.isInformationGap);

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
    ]);
  };

  const g = rules.data?.informationGap;

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

      <Async state={clusters}>
        {() => (
          <>
            <div className="kpi-grid kpi-grid-3">
              <Kpi icon="gap" label="Aktywne luki" value={gaps.length} tone={gaps.some((c) => c.riskTopics.length) ? 'critical' : undefined} hint={`${gaps.filter((c) => c.riskTopics.length).length} w tematach wysokiego ryzyka`} />
              <Kpi icon="history" label="Zapytania bez dowodów (okno)" value={gaps.reduce((s, c) => s + c.noEvidence, 0)} hint="w grupach uznanych za luki" />
              <Kpi icon="folder" label="Luki bez sprawy" value={gaps.filter((c) => !c.caseId).length} hint="wymagają decyzji moderatora" />
            </div>

            <div className="toolbar">
              <SearchInput value={search} onChange={setSearch} placeholder="Szukaj tematu…" />
            </div>

            <Card title="Luki informacyjne" subtitle="Spełniają próg reguły — utwórz sprawę albo przekaż analitykowi." padded={false}>
              {gaps.length === 0 ? (
                <EmptyState title="Brak luk informacyjnych" icon="check">
                  Żadna grupa zapytań nie przekracza progu reguły.
                </EmptyState>
              ) : (
                <GapTable rows={gaps} onOpen={setSelected} />
              )}
            </Card>

            {watch.length > 0 && (
              <Card title="Obserwowane" subtitle="Wysoki odsetek braku dowodów, ale za mało zapytań, by uznać to za lukę." padded={false}>
                <GapTable rows={watch} onOpen={setSelected} />
              </Card>
            )}
          </>
        )}
      </Async>

      <ClusterDrawer cluster={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function GapTable({ rows, onOpen }: { rows: QueryCluster[]; onOpen: (c: QueryCluster) => void }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Temat</th>
            <th className="num">Bez dowodów</th>
            <th>Trend 48 h</th>
            <th>Kanały</th>
            <th>Ostatnie</th>
            <th>Sprawa</th>
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
                {Object.entries(c.channels)
                  .map(([k, v]) => `${channelLabel(k)} ${v}`)
                  .join(' · ')}
              </td>
              <td className="small nowrap">{fmtRelative(c.lastSeen)}</td>
              <td>
                {c.caseId ? (
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
