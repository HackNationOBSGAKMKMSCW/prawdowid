import { useState } from 'react';
import { getApi } from '../api/index.ts';
import type { QueryCluster, Verdict } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Sparkline } from '../components/charts.tsx';
import { ClusterDrawer } from '../components/ClusterDrawer.tsx';
import { Icon } from '../components/icons.tsx';
import { VERDICT } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, PageHeader, SearchInput, Toggle } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportCsv } from '../utils/export.ts';
import { fmtRelative } from '../utils/format.ts';

function dominant(verdicts: QueryCluster['verdicts']): Verdict | null {
  const entries = Object.entries(verdicts) as [Verdict, number][];
  if (!entries.length) return null;
  return entries.sort((a, b) => b[1] - a[1])[0][0];
}

export default function RepeatedPage() {
  const api = getApi();
  const { can } = useAuth();
  const [search, setSearch] = useState('');
  const [onlySurging, setOnlySurging] = useState(false);
  const [selected, setSelected] = useState<QueryCluster | null>(null);
  const clusters = useAsync(() => api.listClusters({ onlySurging }), [onlySurging]);
  const rules = useAsync(() => api.getAlertRules(), []);

  const rows = (clusters.data ?? []).filter(
    (c) =>
      !search.trim() ||
      c.label.toLowerCase().includes(search.trim().toLowerCase()) ||
      c.keywords.some((k) => k.toLowerCase().includes(search.trim().toLowerCase())),
  );
  const s = rules.data?.querySurge;

  return (
    <>
      <PageHeader
        title="Powtarzające się zapytania"
        description="Podobne pytania są grupowane. Szybko rosnąca grupa oznacza, że wiele osób pyta o to samo — warto sprawdzić, czy odpowiedź systemu jest wystarczająca i czy potrzebny jest komunikat."
        actions={
          can('export') ? (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                exportCsv('powtarzajace-sie-zapytania', rows, [
                  { header: 'temat', value: (c) => c.label },
                  { header: 'okno', value: (c) => c.inWindow },
                  { header: 'poprzednie okno', value: (c) => c.previousWindow },
                  { header: 'łącznie', value: (c) => c.total },
                  { header: 'dominujący wynik', value: (c) => { const d = dominant(c.verdicts); return d ? VERDICT[d].label : ''; } },
                  { header: 'słowa kluczowe', value: (c) => c.keywords.join(', ') },
                ])
              }
            >
              <Icon name="download" size={16} /> CSV
            </button>
          ) : undefined
        }
      />

      {s && (
        <div className="rule-strip">
          <Icon name="sliders" size={16} />
          <span>
            Alert „dużo zapytań o to samo”: ≥ <strong>{s.minQueries}</strong> zapytań w <strong>{s.windowHours} h</strong> i
            wzrost ≥ <strong>×{s.growthFactor}</strong> względem poprzedniego okna.
          </span>
        </div>
      )}

      <div className="toolbar">
        <SearchInput value={search} onChange={setSearch} placeholder="Szukaj tematu lub słowa kluczowego…" />
        <Toggle checked={onlySurging} onChange={setOnlySurging} label="Tylko szybko rosnące" />
      </div>

      <Card padded={false}>
        <Async state={clusters}>
          {() =>
            rows.length === 0 ? (
              <EmptyState title="Brak grup zapytań dla filtrów" icon="repeat" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Grupa zapytań</th>
                      <th className="num">Okno</th>
                      <th className="num">Poprzednio</th>
                      <th className="num">Zmiana</th>
                      <th>Trend 48 h</th>
                      <th>Najczęstszy wynik</th>
                      <th>Ostatnie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => {
                      const d = dominant(c.verdicts);
                      const growth = c.inWindow / Math.max(1, c.previousWindow);
                      return (
                        <tr key={c.id} className="clickable" onClick={() => setSelected(c)}>
                          <td>
                            <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); setSelected(c); }}>
                              {c.label}
                            </button>
                            <div className="row gap-xs wrap">
                              {c.isSurging && <Badge tone="warning">Szybki wzrost</Badge>}
                              {c.isInformationGap && <Badge tone="serious">Luka</Badge>}
                              {c.riskTopics.map((r) => (
                                <Badge key={r} tone="critical">
                                  {r}
                                </Badge>
                              ))}
                            </div>
                          </td>
                          <td className="num">
                            <strong>{c.inWindow}</strong>
                          </td>
                          <td className="num">{c.previousWindow}</td>
                          <td className="num nowrap">{c.previousWindow === 0 && c.inWindow > 0 ? 'nowa' : `×${growth.toFixed(1)}`}</td>
                          <td>
                            <Sparkline values={c.hourly} label={`Trend: ${c.label}`} />
                          </td>
                          <td>{d ? <Badge tone={VERDICT[d].tone}>{VERDICT[d].label}</Badge> : <span className="muted">—</span>}</td>
                          <td className="small nowrap">{fmtRelative(c.lastSeen)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
      </Card>

      <ClusterDrawer cluster={selected} onClose={() => setSelected(null)} />
    </>
  );
}
