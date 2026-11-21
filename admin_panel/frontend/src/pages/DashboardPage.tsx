import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { Verdict } from '../api/types.ts';
import { BarList, StackedBar, TargetMeter, TimeSeriesChart } from '../components/charts.tsx';
import { Icon } from '../components/icons.tsx';
import { ALERT_TYPE, channelLabel, SEVERITY, VERDICT } from '../components/labels.ts';
import { Async, Badge, Card, Kpi, PageHeader, Tabs } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime, fmtDuration, fmtInt, fmtPct, fmtPln, fmtRelative, fmtTime } from '../utils/format.ts';

const RANGES = [
  { value: '24', label: '24 h' },
  { value: '48', label: '48 h' },
  { value: '168', label: '7 dni' },
] as const;

const VERDICT_ORDER: Verdict[] = ['confirmed', 'false', 'misleading', 'insufficient', 'not_verifiable'];

export default function DashboardPage() {
  const api = getApi();
  const [range, setRange] = useState<(typeof RANGES)[number]['value']>('24');
  const stats = useAsync(() => api.getDashboard(Number(range)), [range]);
  const alerts = useAsync(() => api.listAlerts({ status: 'open' }), []);
  const gaps = useAsync(() => api.listClusters({ onlyGaps: true }), []);

  return (
    <>
      <PageHeader
        title="Pulpit"
        description="Stan usługi weryfikacji: ruch, wstrzymania się od rozstrzygnięcia, jakość i sygnały wymagające reakcji."
        actions={<Tabs label="Zakres czasu" value={range} onChange={setRange} options={[...RANGES]} />}
      />

      <Async state={stats}>
        {(s) => (
          <>
            <div className="kpi-grid">
              <Kpi icon="history" label="Sprawdzenia" value={fmtInt(s.checks)} hint={`w ciągu ${range === '168' ? '7 dni' : `${range} h`}`} />
              <Kpi
                icon="gap"
                label="Wstrzymano się (brak dowodów)"
                value={fmtPct(s.checks ? s.abstained / s.checks : 0)}
                hint={`${fmtInt(s.abstained)} zapytań`}
              />
              <Kpi icon="refresh" label="Mediana czasu odpowiedzi" value={fmtDuration(s.medianLatencyMs)} hint={`p95: ${fmtDuration(s.p95LatencyMs)} · cel ≤ 30 s`} />
              <Kpi icon="cpu" label="Koszt na 1000 zapytań" value={fmtPln(s.costPer1000Pln)} hint={`łącznie ${fmtPln(s.costTotalPln)} (szacunek)`} />
              <Kpi
                icon="bell"
                label="Aktywne alerty"
                value={fmtInt(s.activeAlerts)}
                tone={s.criticalAlerts > 0 ? 'critical' : undefined}
                hint={s.criticalAlerts > 0 ? `${s.criticalAlerts} krytyczne` : 'brak krytycznych'}
              />
              <Kpi icon="folder" label="Otwarte sprawy" value={fmtInt(s.openCases)} hint={`${s.informationGaps} luk informacyjnych`} />
            </div>

            <div className="grid-2-1">
              <Card
                title="Zapytania w czasie"
                subtitle="Wszystkie sprawdzenia oraz te, w których system wstrzymał się od rozstrzygnięcia."
              >
                <TimeSeriesChart
                  ariaLabel="Liczba zapytań w czasie"
                  labels={s.series.map((p) => (Number(range) <= 48 ? fmtTime(p.t) : fmtDateTime(p.t).replace(/,? \d\d:\d\d$/, '')))}
                  series={[
                    { key: 'total', label: 'Wszystkie zapytania', color: 'var(--series-1)', values: s.series.map((p) => p.total), area: true },
                    { key: 'abstained', label: 'Brak wystarczających dowodów', color: 'var(--series-2)', values: s.series.map((p) => p.abstained) },
                  ]}
                />
                <div className="chart-foot muted small">
                  Błędy techniczne: {s.technicalErrors} (raportowane osobno, nie są werdyktem) · Odparte próby prompt
                  injection: {s.injectionsBlocked}
                </div>
              </Card>

              <Card title="Wyniki sprawdzeń" subtitle="Rozkład werdyktów w wybranym okresie.">
                <StackedBar
                  ariaLabel="Rozkład werdyktów"
                  segments={VERDICT_ORDER.map((v) => ({
                    key: v,
                    label: VERDICT[v].label,
                    value: s.verdicts[v] ?? 0,
                    tone: VERDICT[v].tone,
                  }))}
                />
                <h3 className="subhead">Kanały</h3>
                <BarList
                  items={Object.entries(s.channels)
                    .sort((a, b) => b[1] - a[1])
                    .map(([ch, n]) => ({ key: ch, label: channelLabel(ch), value: n }))}
                />
              </Card>
            </div>

            <div className="grid-2">
              <Card
                title="Wymagają uwagi"
                subtitle="Otwarte alerty, od najpoważniejszych."
                actions={
                  <Link to="/alerts" className="btn btn-sm btn-ghost">
                    Wszystkie <Icon name="arrowRight" size={14} />
                  </Link>
                }
                padded={false}
              >
                <Async state={alerts}>
                  {(list) =>
                    list.length === 0 ? (
                      <p className="card-body muted">Brak otwartych alertów.</p>
                    ) : (
                      <ul className="list">
                        {list.slice(0, 6).map((a) => (
                          <li key={a.id}>
                            <Link to={`/alerts?focus=${encodeURIComponent(a.id)}`} className="list-link">
                              <Badge tone={SEVERITY[a.severity].tone}>{SEVERITY[a.severity].label}</Badge>
                              <span className="list-main">
                                <span className="list-title">{a.title}</span>
                                <span className="muted small">
                                  {ALERT_TYPE[a.type].label} · {fmtRelative(a.updatedAt)}
                                </span>
                              </span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )
                  }
                </Async>
              </Card>

              <Card
                title="Luki informacyjne"
                subtitle="Tematy, o które pytają ludzie, a w katalogu brakuje źródeł."
                actions={
                  <Link to="/gaps" className="btn btn-sm btn-ghost">
                    Szczegóły <Icon name="arrowRight" size={14} />
                  </Link>
                }
              >
                <Async state={gaps}>
                  {(list) =>
                    list.length === 0 ? (
                      <p className="muted">Brak luk informacyjnych.</p>
                    ) : (
                      <BarList
                        items={list.slice(0, 6).map((g) => ({
                          key: g.id,
                          label: g.label,
                          value: g.noEvidence,
                          hint: `${fmtPct(g.noEvidenceRatio)} zapytań bez dowodów`,
                        }))}
                        format={(v) => `${v} bez dowodów`}
                      />
                    )
                  }
                </Async>
              </Card>
            </div>

            <Card
              title="Jakość weryfikacji — mierniki obowiązkowe"
              subtitle={
                <>
                  Wynik ostatniej ewaluacji na zestawie referencyjnym ({fmtDateTime(s.qualityEvaluatedAt)}).
                  {api.mode === 'mock' && ' W trybie demo wartości są przykładowe.'}
                </>
              }
            >
              <div className="quality-grid">
                {s.quality.map((m) => {
                  const ok = m.direction === 'min' ? m.value >= m.target : m.value <= m.target;
                  const fmt = (v: number) => (m.unit === '' ? v.toFixed(2).replace('.', ',') : `${String(v).replace('.', ',')}${m.unit === '%' ? '%' : ' s'}`);
                  return (
                    <div key={m.key} className="quality-item">
                      <div className="quality-head">
                        <span>{m.label}</span>
                        <Badge tone={ok ? 'good' : 'critical'}>{ok ? 'Cel spełniony' : 'Poniżej celu'}</Badge>
                      </div>
                      <div className="quality-value">
                        {fmt(m.value)}
                        <span className="muted small">
                          {' '}
                          cel {m.direction === 'min' ? '≥' : '≤'} {fmt(m.target)}
                        </span>
                      </div>
                      <TargetMeter
                        value={m.value}
                        target={m.target}
                        direction={m.direction}
                        max={m.unit === '%' ? 100 : m.unit === 's' ? 40 : 1}
                        format={fmt}
                      />
                    </div>
                  );
                })}
              </div>
            </Card>
          </>
        )}
      </Async>
    </>
  );
}
