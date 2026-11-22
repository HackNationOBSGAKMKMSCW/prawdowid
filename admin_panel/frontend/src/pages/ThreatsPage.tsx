import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { CriticalQueryEvent, InjectionEvent, IpBlock, ThreatReport, ThreatSubject } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { BarList, TimeSeriesChart } from '../components/charts.tsx';
import { Icon } from '../components/icons.tsx';
import { channelLabel, safetyLabel } from '../components/labels.ts';
import { Async, Badge, Card, EmptyState, Kpi, PageHeader, Tabs, useAction } from '../components/ui.tsx';
import { useAsync } from '../hooks/useAsync.ts';
import { exportJson } from '../utils/export.ts';
import { fmtDateTime, fmtInt, fmtRelative, fmtTime, plural, truncate } from '../utils/format.ts';

const RANGES = [
  { value: '24', label: '24 h' },
  { value: '48', label: '48 h' },
  { value: '168', label: '7 dni' },
  { value: '720', label: '30 dni' },
] as const;

/** Where the instructions were found. */
const INJECTION_SOURCE: Record<string, string> = {
  input: 'Wiadomość użytkownika',
  text: 'Analizowany tekst',
  url: 'Treść strony z linku',
  source: 'Pobrane źródło',
  truth_source: 'Pobrane źródło',
};

const DETECTOR: Record<string, string> = {
  monitor: 'Monitor zapytań',
  InputSanitizer: 'Filtr wejścia analizy',
  observability: 'Wzorce observability',
};

const KIND: Record<string, string> = {
  input_pattern: 'bezpośrednia',
  indirect: 'pośrednia (w źródle)',
  source_pattern: 'pośrednia (w źródle)',
};

const ALERT_STATUS_LABEL: Record<string, { label: string; tone: 'info' | 'neutral' | 'good' | 'muted' }> = {
  otwarty: { label: 'Otwarty', tone: 'info' },
  w_analizie: { label: 'W analizie', tone: 'neutral' },
  rozwiazany: { label: 'Rozwiązany', tone: 'good' },
  falszywy_alarm: { label: 'Fałszywy alarm', tone: 'muted' },
};

const SEVERITY_LABEL: Record<string, { label: string; tone: 'critical' | 'serious' | 'warning' | 'neutral' }> = {
  wysoki: { label: 'Wysokie ryzyko', tone: 'critical' },
  wysoka: { label: 'Wysoka', tone: 'critical' },
  sredni: { label: 'Średnie ryzyko', tone: 'serious' },
  srednia: { label: 'Średnia', tone: 'serious' },
  brak: { label: 'Brak', tone: 'neutral' },
};

const REFUSAL: Record<string, string> = {
  niebezpieczna_tresc: 'prośba o instrukcje — odrzucona',
  ip_zablokowany: 'adres zablokowany (prompt injection)',
};

export default function ThreatsPage() {
  const api = getApi();
  const { can } = useAuth();
  const [range, setRange] = useState<(typeof RANGES)[number]['value']>('24');
  const hours = Number(range);
  const report = useAsync(() => api.getThreats(hours), [hours]);
  const { reload } = report;

  // Logi napływają na bieżąco: odświeżanie co minutę, gdy karta jest widoczna.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') reload();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  return (
    <>
      <PageHeader
        title="Zagrożenia"
        description="Na podstawie logów serwisu (strona WWW i WhatsApp): próby prompt injection, skoordynowane sprawdzanie fałszywych informacji i zapytania o treści krytyczne, np. terroryzm. Odświeża się co minutę."
        actions={
          <>
            <Tabs label="Zakres czasu" value={range} onChange={setRange} options={[...RANGES]} />
            <button type="button" className="btn btn-sm" onClick={reload} disabled={report.loading}>
              <Icon name="refresh" size={16} /> Odśwież
            </button>
            {can('export') && report.data && (
              <button type="button" className="btn btn-sm" onClick={() => exportJson('zagrozenia', report.data)}>
                <Icon name="download" size={16} /> JSON
              </button>
            )}
          </>
        }
      />
      <Async state={report}>{(r) => <ThreatView report={r} />}</Async>
    </>
  );
}

function ThreatView({ report: r }: { report: ThreatReport }) {
  const s = r.summary;
  const quiet = s.promptInjection + s.manipulationCampaigns + s.criticalQueries === 0;
  return (
    <>
      {!r.logAvailable && (
        <div className="notice notice-warning">
          <Icon name="alert" size={16} />
          <div>
            <strong>Brak pliku logów.</strong> Serwer nie zapisał jeszcze żadnych zdarzeń do{' '}
            <span className="mono">{r.file}</span>. Logi zapisuje <span className="mono">server:app</span> (zmienne{' '}
            <span className="mono">LOG_ENABLED</span>, <span className="mono">LOG_FILE</span>).
          </div>
        </div>
      )}

      <div className="kpi-grid kpi-grid-4">
        <Kpi
          icon="shield"
          label="Próby prompt injection"
          value={fmtInt(s.promptInjection)}
          tone={s.promptInjection ? 'critical' : undefined}
          hint={r.injection.repeatedTexts ? `${r.injection.repeatedTexts} powtarzanych tekstów` : 'w tym okresie'}
        />
        <Kpi
          icon="repeat"
          label="Ataki manipulacyjne"
          value={fmtInt(s.manipulationCampaigns)}
          tone={s.manipulationCampaigns ? 'serious' : undefined}
          hint="wiele zapytań o ten sam fałsz w krótkim czasie"
        />
        <Kpi
          icon="alert"
          label="Informacje krytyczne"
          value={fmtInt(s.criticalQueries)}
          tone={s.criticalQueries ? 'warning' : undefined}
          hint="terroryzm, broń, materiały wybuchowe, przemoc"
        />
        <Kpi
          icon="lock"
          label="Odrzucone prośby"
          value={fmtInt(s.refused)}
          tone={s.refused ? 'warning' : undefined}
          hint="instrukcje lub zdobycie broni i materiałów wybuchowych"
        />
      </div>

      {quiet ? (
        <Card>
          <EmptyState title="Brak zagrożeń w tym okresie" icon="shield">
            Przejrzano {fmtInt(r.eventsScanned)} zdarzeń z logów od {fmtDateTime(r.since)}.
          </EmptyState>
        </Card>
      ) : (
        <Card title="Zdarzenia w czasie" subtitle={`${fmtInt(r.eventsScanned)} zdarzeń z logów od ${fmtDateTime(r.since)}`}>
          <TimeSeriesChart
            ariaLabel="Zagrożenia w czasie"
            height={200}
            labels={r.timeline.map((b) => (r.hours <= 48 ? fmtTime(b.bucket) : fmtDateTime(b.bucket).replace(/,? \d\d:\d\d$/, '')))}
            series={[
              { key: 'injection', label: 'Prompt injection', color: 'var(--status-critical)', values: r.timeline.map((b) => b.promptInjection) },
              { key: 'manipulation', label: 'Ataki manipulacyjne', color: 'var(--series-2)', values: r.timeline.map((b) => b.manipulation) },
              { key: 'critical', label: 'Informacje krytyczne', color: 'var(--series-1)', values: r.timeline.map((b) => b.critical) },
            ]}
          />
        </Card>
      )}

      <InjectionSection report={r} />
      {supports('ipBlocks') && <BlockedAddresses />}
      <ManipulationSection report={r} />
      <CriticalSection report={r} />
    </>
  );
}

/** Where it came from: only the channel; the panel keeps no data about the person. */
function Who({ item }: { item: ThreatSubject }) {
  return <div className="small">{item.channel ? channelLabel(item.channel) : <span className="muted">—</span>}</div>;
}

function Links({ item }: { item: ThreatSubject & { requestId: string | null } }) {
  return (
    <div className="row gap-xs wrap">
      {item.queryId && (
        <Link className="btn btn-xs" to={`/checks?focus=${encodeURIComponent(item.queryId)}`}>
          Zapytanie
        </Link>
      )}
      {item.requestId && supports('techEvents') && (
        <Link className="btn btn-xs btn-ghost" to={`/logs?request=${encodeURIComponent(item.requestId)}`}>
          Log
        </Link>
      )}
    </div>
  );
}

function countItems(counts: Record<string, number>, label: (key: string) => string) {
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, label: label(key), value }));
}

/** Addresses blocked after prompt injection (masked; the backend never stores the address). */
function BlockedAddresses() {
  const api = getApi();
  const { can } = useAuth();
  const { run, busy } = useAction();
  const blocks = useAsync<IpBlock[]>(() => api.listIpBlocks(true), []);
  const unblock = async (key: string) => {
    if (await run(() => api.unblockIp(key), 'Adres odblokowany.')) blocks.reload();
  };
  return (
    <Card
      title="Zablokowane adresy"
      subtitle="Adresy IP zablokowane po próbach prompt injection. Panel pokazuje tylko maskę; w bazie jest skrót (HMAC), nie adres."
      padded={false}
    >
      <Async state={blocks}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState title="Żaden adres nie jest zablokowany" icon="lock" />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Adres</th>
                    <th>Do kiedy</th>
                    <th className="num">Próby</th>
                    <th>Kto</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.map((b) => (
                    <tr key={b.key}>
                      <td className="mono">{b.label}</td>
                      <td className="small nowrap">{b.permanent ? 'bez terminu' : fmtDateTime(b.blockedUntil ?? '')}</td>
                      <td className="num">{b.attempts}</td>
                      <td className="small">{b.blockedBy === 'auto' ? 'automatycznie' : b.blockedBy}</td>
                      <td>
                        <div className="row gap-xs">
                          {b.alertId && (
                            <Link className="btn btn-xs" to={`/alerts?focus=${encodeURIComponent(b.alertId)}&status=any&type=prompt_injection`}>
                              Alert
                            </Link>
                          )}
                          {can('security:write') && (
                            <button type="button" className="btn btn-xs" disabled={busy} onClick={() => unblock(b.key)}>
                              Odblokuj
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Async>
    </Card>
  );
}

function InjectionSection({ report: r }: { report: ThreatReport }) {
  const items = r.injection.recent;
  return (
    <div className="grid-2-1">
      <Card
        title="Próby prompt injection"
        subtitle="Teksty z poleceniami dla modelu (np. „zignoruj poprzednie instrukcje”). Serwis traktuje je wyłącznie jako dane — nic nie wykonuje."
        padded={false}
      >
        {items.length === 0 ? (
          <EmptyState title="Brak prób w tym okresie" icon="shield" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Czas</th>
                  <th>Fragment</th>
                  <th>Skąd</th>
                  <th>Kanał</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((e, i) => (
                  <InjectionRow key={`${e.at}-${e.requestId ?? i}`} event={e} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Skąd pochodzą">
        {items.length === 0 ? (
          <p className="muted small">Brak danych.</p>
        ) : (
          <>
            <BarList items={countItems(r.injection.bySource, (k) => INJECTION_SOURCE[k] ?? k)} />
            <h4 className="small muted" style={{ margin: '16px 0 8px' }}>
              Wykryte przez
            </h4>
            <BarList items={countItems(r.injection.byDetector, (k) => DETECTOR[k] ?? k)} />
          </>
        )}
      </Card>
    </div>
  );
}

function InjectionRow({ event: e }: { event: InjectionEvent }) {
  return (
    <tr>
      <td className="small nowrap">
        {fmtTime(e.at)}
        <div className="muted">{fmtRelative(e.at)}</div>
      </td>
      <td>
        <div className="mono small">„{e.snippet ?? '—'}”</div>
        {e.text && e.text !== e.snippet && <div className="muted small">{truncate(e.text, 140)}</div>}
        {e.repeats > 1 && (
          <Badge tone="critical" title="Ten sam tekst w tym okresie">
            powtórzony {e.repeats}×
          </Badge>
        )}
      </td>
      <td className="small">
        {INJECTION_SOURCE[e.source ?? ''] ?? e.source ?? '—'}
        <div className="muted">
          {KIND[e.kind ?? ''] ?? e.kind ?? ''}
          {e.detector && ` · ${DETECTOR[e.detector] ?? e.detector}`}
        </div>
      </td>
      <td>
        <Who item={e} />
      </td>
      <td>
        <Links item={e} />
      </td>
    </tr>
  );
}

function ManipulationSection({ report: r }: { report: ThreatReport }) {
  return (
    <Card
      title="Ataki manipulacyjne"
      subtitle="W krótkim czasie wiele zapytań o to samo twierdzenie ocenione jako fałsz — możliwa skoordynowana kampania dezinformacyjna."
    >
      {r.campaigns.length === 0 ? (
        <EmptyState title="Brak podejrzanych kampanii w tym okresie" icon="repeat" />
      ) : (
        <ul className="threat-list">
          {r.campaigns.map((c) => {
            const status = ALERT_STATUS_LABEL[c.status ?? ''];
            const severity = SEVERITY_LABEL[c.severity ?? ''];
            return (
              <li key={c.alertId ?? c.firstSignal} className="threat-item">
                <div className="row gap-xs wrap">
                  {severity && <Badge tone={severity.tone}>{severity.label}</Badge>}
                  {status && <Badge tone={status.tone}>{status.label}</Badge>}
                  <strong>{c.claim ?? c.title}</strong>
                </div>
                <div className="small muted">
                  {c.count !== null && `${c.count} ${plural(c.count, ['sprawdzenie', 'sprawdzenia', 'sprawdzeń'])} fałszu`}
                  {` · od ${fmtDateTime(c.firstSignal)} do ${fmtDateTime(c.lastSignal)}`}
                  {` · ${c.signals} ${plural(c.signals, ['sygnał', 'sygnały', 'sygnałów'])} w logach`}
                </div>
                <div className="row gap-xs wrap">
                  <Link className="btn btn-xs" to="/alerts">
                    Alerty
                  </Link>
                  {c.topicId && (
                    <Link className="btn btn-xs btn-ghost" to={`/checks?cluster=${encodeURIComponent(c.topicId)}`}>
                      Zapytania
                    </Link>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function CriticalSection({ report: r }: { report: ThreatReport }) {
  const items = r.critical.recent;
  return (
    <div className="grid-2-1">
      <Card
        title="Informacje krytyczne"
        subtitle="Zapytania o terroryzm, broń, materiały wybuchowe i przemoc. Prośby o instrukcje są odrzucane bez sprawdzania."
        padded={false}
      >
        {items.length === 0 ? (
          <EmptyState title="Brak zapytań krytycznych w tym okresie" icon="alert" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Czas</th>
                  <th>Zapytanie</th>
                  <th>Kategorie</th>
                  <th>Kanał</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((e, i) => (
                  <CriticalRow key={`${e.at}-${e.queryId ?? i}`} event={e} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Kategorie">
        {Object.keys(r.critical.byCategory).length === 0 ? (
          <p className="muted small">Brak danych.</p>
        ) : (
          <BarList items={countItems(r.critical.byCategory, safetyLabel)} />
        )}
      </Card>
    </div>
  );
}

function CriticalRow({ event: e }: { event: CriticalQueryEvent }) {
  const severity = SEVERITY_LABEL[e.severity ?? ''];
  return (
    <tr>
      <td className="small nowrap">
        {fmtTime(e.at)}
        <div className="muted">{fmtRelative(e.at)}</div>
      </td>
      <td>
        <div className="small">{e.text ? truncate(e.text, 140) : <span className="muted">treść niedostępna</span>}</div>
        {e.refused && <Badge tone="critical">{REFUSAL[e.reason ?? ''] ?? 'odrzucone'}</Badge>}
      </td>
      <td>
        <div className="row gap-xs wrap">
          {severity && <Badge tone={severity.tone}>{severity.label}</Badge>}
          {e.categories.map((c) => (
            <Badge key={c} tone="neutral">
              {safetyLabel(c)}
            </Badge>
          ))}
        </div>
      </td>
      <td>
        <Who item={e} />
      </td>
      <td>
        <Links item={e} />
      </td>
    </tr>
  );
}
