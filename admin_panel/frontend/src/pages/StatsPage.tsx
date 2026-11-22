import { useState } from 'react';
import { getApi, supports } from '../api/index.ts';
import type { Verdict } from '../api/types.ts';
import { BarList, StackedBar, TimeSeriesChart } from '../components/charts.tsx';
import { channelLabel, VERDICT } from '../components/labels.ts';
import { Async, Card, Kpi, PageHeader, Tabs } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { fmtDateTime, fmtDuration, fmtInt, fmtPct, fmtPln, fmtTime, plural } from '../utils/format.ts';

const RANGES = [
  { value: '24', label: '24 h' },
  { value: '48', label: '48 h' },
  { value: '168', label: '7 dni' },
] as const;

const VERDICT_ORDER: Verdict[] = ['confirmed', 'false', 'misleading', 'insufficient', 'not_verifiable'];

export default function StatsPage() {
  const api = getApi();
  const [range, setRange] = useState<(typeof RANGES)[number]['value']>('24');
  const stats = useAsync(() => api.getDashboard(Number(range)), [range]);
  const clusters = useAsync(() => api.listClusters(), []);
  const rangeLabel = range === '168' ? '7 dni' : `${range} h`;

  return (
    <>
      <PageHeader
        title="Statystyki"
        description="Ruch w usłudze, wyniki sprawdzeń, czas odpowiedzi i koszt."
        actions={<Tabs label="Zakres czasu" value={range} onChange={setRange} options={[...RANGES]} />}
      />

      <Async state={stats}>
        {(s) => (
          <>
            <div className="kpi-grid">
              <Kpi icon="history" label="Sprawdzenia" value={fmtInt(s.checks)} hint={`w ciągu ${rangeLabel}`} />
              <Kpi
                icon="gap"
                label="Bez wystarczających dowodów"
                value={fmtPct(s.checks ? s.abstained / s.checks : 0)}
                hint={`${fmtInt(s.abstained)} zapytań`}
              />
              <Kpi icon="refresh" label="Typowy czas odpowiedzi" value={fmtDuration(s.medianLatencyMs)} hint={`najwolniejsze 5%: ${fmtDuration(s.p95LatencyMs)}`} />
              {supports('checkCost') ? (
                <Kpi icon="cpu" label="Koszt 1000 sprawdzeń" value={fmtPln(s.costPer1000Pln)} hint={`łącznie ${fmtPln(s.costTotalPln)} (szacunek)`} />
              ) : (
                <Kpi icon="users" label="Użytkownicy" value={fmtInt(s.users ?? 0)} hint={`${s.blockedUsers ?? 0} zablokowanych teraz`} />
              )}
              {s.dangerousQueries !== undefined && (
                <Kpi
                  icon="alert"
                  label="Treści niebezpieczne"
                  value={fmtInt(s.dangerousQueries)}
                  tone={s.dangerousQueries ? 'warning' : undefined}
                  hint={`${fmtInt(s.refused ?? 0)} zapytań odrzuconych`}
                />
              )}
            </div>

            <div className="grid-2-1">
              <Card title="Zapytania w czasie" subtitle="Wszystkie sprawdzenia oraz te, w których system nie znalazł wystarczających dowodów.">
                <TimeSeriesChart
                  ariaLabel="Liczba zapytań w czasie"
                  labels={s.series.map((p) => (Number(range) <= 48 ? fmtTime(p.t) : fmtDateTime(p.t).replace(/,? \d\d:\d\d$/, '')))}
                  series={[
                    { key: 'total', label: 'Wszystkie zapytania', color: 'var(--series-1)', values: s.series.map((p) => p.total), area: true },
                    { key: 'abstained', label: 'Brak wystarczających dowodów', color: 'var(--series-2)', values: s.series.map((p) => p.abstained) },
                  ]}
                />
                <div className="chart-foot muted small">
                  Błędy techniczne: {s.technicalErrors} (nie są werdyktem) ·{' '}
                  {s.refused === undefined
                    ? `Odparte próby manipulacji: ${s.injectionsBlocked}`
                    : `Odrzucone (blokada lub treść wysokiego ryzyka): ${s.refused}`}
                  {s.pending ? ` · W toku lub przerwane: ${s.pending}` : ''}
                </div>
              </Card>

              <Card title="Wyniki sprawdzeń">
                <StackedBar
                  ariaLabel="Rozkład werdyktów"
                  segments={VERDICT_ORDER.map((v) => ({ key: v, label: VERDICT[v].label, value: s.verdicts[v] ?? 0, tone: VERDICT[v].tone }))}
                />
                <h3 className="subhead">Kanały</h3>
                <BarList
                  items={Object.entries(s.channels)
                    .sort((a, b) => b[1] - a[1])
                    .map(([ch, n]) => ({ key: ch, label: channelLabel(ch), value: n }))}
                />
              </Card>
            </div>
          </>
        )}
      </Async>

      <Card
        title={supports('clusters') ? 'Najczęstsze tematy pytań' : 'Tematy bez rozstrzygnięcia'}
        subtitle={
          supports('clusters')
            ? 'Grupy podobnych zapytań, liczone od początku okresu przechowywania.'
            : 'Tematy, o które pytano, a system nie znalazł rozstrzygnięcia (luki i podejrzenia luk), według liczby twierdzeń.'
        }
      >
        <Async state={clusters}>
          {(list) => (
            <BarList
              items={[...list]
                .sort((a, b) => b.total - a.total)
                .slice(0, 8)
                .map((c) => ({ key: c.id, label: c.label, value: c.total }))}
              format={(v) => `${v} ${supports('clusters') ? 'zapytań' : plural(v, ['twierdzenie', 'twierdzenia', 'twierdzeń'])}`}
            />
          )}
        </Async>
      </Card>
    </>
  );
}
