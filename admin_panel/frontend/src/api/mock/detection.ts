/**
 * Reference implementation of the alert rules, used by the demo data source.
 * The real backend runs the same rules server-side; keeping them as pure
 * functions makes them easy to port and to test.
 *
 *  - information gap: many similar questions in a window, most of them ended
 *    without evidence ("brak wystarczających dowodów"),
 *  - query surge: many questions about the same thing, growing fast,
 *  - high risk: the group matches a high-risk topic (e.g. terrorism) — the
 *    designated people are notified, the system still gives no verdict,
 *  - prompt injection, incident matches, source-status warnings, technical
 *    failures — each reported separately from verdicts.
 */
import type {
  Alert,
  AlertRules,
  AlertType,
  CheckRecord,
  QueryCluster,
  RiskTopic,
  Role,
  SecurityEvent,
  Severity,
  Verdict,
} from '../types.ts';

const HOUR = 3_600_000;

export interface ClusterMeta {
  id: string;
  label: string;
  keywords: string[];
  missing?: string;
}

export function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

export function matchRiskTopics(texts: string[], topics: RiskTopic[]): RiskTopic[] {
  const haystack = normalizeText(texts.join(' \n '));
  return topics.filter((topic) =>
    topic.keywords.some((kw) => kw.trim() && haystack.includes(normalizeText(kw.trim()))),
  );
}

const SEVERITY_ORDER: Severity[] = ['low', 'medium', 'high', 'critical'];

export function maxSeverity(...values: Severity[]): Severity {
  return values.reduce((a, b) => (SEVERITY_ORDER.indexOf(b) > SEVERITY_ORDER.indexOf(a) ? b : a), 'low');
}

export function buildClusters(
  checks: CheckRecord[],
  metas: ClusterMeta[],
  rules: AlertRules,
  now: number,
): QueryCluster[] {
  const byCluster = new Map<string, CheckRecord[]>();
  for (const check of checks) {
    if (!check.clusterId) continue;
    const list = byCluster.get(check.clusterId) ?? [];
    list.push(check);
    byCluster.set(check.clusterId, list);
  }

  const surgeWindow = rules.querySurge.windowHours * HOUR;
  const gapWindow = rules.informationGap.windowHours * HOUR;

  const clusters: QueryCluster[] = [];
  for (const meta of metas) {
    const list = byCluster.get(meta.id) ?? [];
    if (list.length === 0) continue;
    const times = list.map((c) => Date.parse(c.createdAt));
    const inWindow = times.filter((t) => now - t <= surgeWindow).length;
    const previousWindow = times.filter((t) => now - t > surgeWindow && now - t <= 2 * surgeWindow).length;
    const inGap = list.filter((c) => now - Date.parse(c.createdAt) <= gapWindow);
    const noEvidence = inGap.filter((c) => c.outcome === 'abstained').length;
    const noEvidenceRatio = inGap.length ? noEvidence / inGap.length : 0;

    const verdicts: Partial<Record<Verdict, number>> = {};
    const channels: Record<string, number> = {};
    for (const c of list) {
      if (c.overallVerdict) verdicts[c.overallVerdict] = (verdicts[c.overallVerdict] ?? 0) + 1;
      channels[c.channel] = (channels[c.channel] ?? 0) + 1;
    }

    const hourly = Array.from({ length: 48 }, () => 0);
    for (const t of times) {
      const idx = 47 - Math.floor((now - t) / HOUR);
      if (idx >= 0 && idx < 48) hourly[idx] += 1;
    }

    const samples = [...new Set(list.map((c) => c.query))].slice(0, 6);
    const risk = rules.highRisk.enabled
      ? matchRiskTopics([meta.label, ...meta.keywords, ...samples], rules.highRisk.topics)
      : [];

    const isInformationGap =
      rules.informationGap.enabled &&
      inGap.length >= rules.informationGap.minQueries &&
      noEvidenceRatio >= rules.informationGap.minNoEvidenceRatio;
    const isSurging =
      rules.querySurge.enabled &&
      inWindow >= rules.querySurge.minQueries &&
      inWindow >= rules.querySurge.growthFactor * Math.max(previousWindow, 1);

    clusters.push({
      id: meta.id,
      label: meta.label,
      keywords: meta.keywords,
      total: list.length,
      inWindow,
      previousWindow,
      // Sessions are not stored in the demo; approximate them from the query count.
      uniqueSessions: Math.max(1, Math.round(list.length * 0.86)),
      noEvidence,
      noEvidenceRatio,
      verdicts,
      channels,
      firstSeen: new Date(Math.min(...times)).toISOString(),
      lastSeen: new Date(Math.max(...times)).toISOString(),
      hourly,
      riskTopics: risk.map((r) => r.label),
      sampleQueries: samples,
      missing: meta.missing,
      isInformationGap,
      isSurging,
    });
  }
  return clusters.sort((a, b) => b.inWindow - a.inWindow || b.total - a.total);
}

export const DEFAULT_RECIPIENT_ROLE: Record<AlertType, Role> = {
  information_gap: 'analyst',
  query_surge: 'admin',
  high_risk: 'analyst',
  prompt_injection: 'admin',
  incident_match: 'analyst',
  source_status: 'admin',
  system: 'admin',
  disinformation: 'analyst',
  dangerous_content: 'admin',
  known_disinformation: 'analyst',
  sql_injection: 'admin',
};

/** An alert as computed from current data — before status and notifications are applied. */
export type AlertDraft = Omit<Alert, 'status' | 'notified' | 'caseId' | 'recommendedRole'>;

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function detectAlerts(
  clusters: QueryCluster[],
  checks: CheckRecord[],
  security: SecurityEvent[],
  rules: AlertRules,
  now: number,
): AlertDraft[] {
  const drafts: AlertDraft[] = [];
  const last = (list: { createdAt?: string; at?: string }[]) =>
    list.map((x) => x.createdAt ?? x.at ?? '').sort().at(-1) ?? new Date(now).toISOString();
  const checksOf = (clusterId: string, hours: number) =>
    checks.filter((c) => c.clusterId === clusterId && now - Date.parse(c.createdAt) <= hours * HOUR);

  for (const cl of clusters) {
    const risky = rules.highRisk.topics.filter((t) => cl.riskTopics.includes(t.label));

    if (cl.isInformationGap) {
      const ids = checksOf(cl.id, rules.informationGap.windowHours).filter((c) => c.outcome === 'abstained');
      const gapCount = Math.round(cl.noEvidence / Math.max(cl.noEvidenceRatio, 0.0001));
      drafts.push({
        id: `information_gap:${cl.id}`,
        type: 'information_gap',
        severity: risky.length ? maxSeverity('high', ...risky.map((t) => t.severity)) : cl.noEvidence >= 3 * rules.informationGap.minQueries ? 'high' : 'medium',
        title: `Luka informacyjna: ${cl.label}`,
        description: `${cl.noEvidence} z ${gapCount} zapytań w ciągu ${rules.informationGap.windowHours} h zakończyło się brakiem wystarczających dowodów. ${cl.missing ?? ''}`.trim(),
        rule: `≥ ${rules.informationGap.minQueries} podobnych zapytań w ${rules.informationGap.windowHours} h i ≥ ${pct(rules.informationGap.minNoEvidenceRatio)} bez dowodów (podobieństwo ≥ ${rules.informationGap.similarityThreshold})`,
        createdAt: ids.map((c) => c.createdAt).sort()[Math.min(rules.informationGap.minQueries, ids.length) - 1] ?? cl.firstSeen,
        updatedAt: last(ids),
        clusterId: cl.id,
        checkIds: ids.map((c) => c.id),
        metrics: {
          'Zapytania w oknie': gapCount,
          'Bez dowodów': cl.noEvidence,
          'Odsetek bez dowodów': pct(cl.noEvidenceRatio),
        },
      });
    }

    // A burst of manipulation attempts is reported by the prompt-injection rule, not as a topic surge.
    const injectionShare =
      checksOf(cl.id, rules.querySurge.windowHours).filter((c) => c.flags.includes('prompt_injection')).length /
      Math.max(1, cl.inWindow);
    if (cl.isSurging && injectionShare < 0.5) {
      const ids = checksOf(cl.id, rules.querySurge.windowHours);
      const growth = cl.inWindow / Math.max(cl.previousWindow, 1);
      drafts.push({
        id: `query_surge:${cl.id}`,
        type: 'query_surge',
        severity: risky.length ? 'high' : growth >= 2 * rules.querySurge.growthFactor ? 'high' : 'medium',
        title: `Dużo zapytań o to samo: ${cl.label}`,
        description: `${cl.inWindow} zapytań w ciągu ${rules.querySurge.windowHours} h (poprzednio ${cl.previousWindow}) — wzrost ×${growth.toFixed(1)}.`,
        rule: `≥ ${rules.querySurge.minQueries} zapytań w ${rules.querySurge.windowHours} h i wzrost ≥ ×${rules.querySurge.growthFactor} względem poprzedniego okna`,
        createdAt: ids.map((c) => c.createdAt).sort()[Math.min(rules.querySurge.minQueries, ids.length) - 1] ?? cl.firstSeen,
        updatedAt: last(ids),
        clusterId: cl.id,
        checkIds: ids.map((c) => c.id),
        metrics: {
          'Zapytania w oknie': cl.inWindow,
          'Poprzednie okno': cl.previousWindow,
          Wzrost: `×${growth.toFixed(1)}`,
        },
      });
    }

    if (risky.length) {
      const recent = checksOf(cl.id, 24);
      if (recent.length > 0 && (rules.highRisk.notifyImmediately || recent.length >= 3)) {
        drafts.push({
          id: `high_risk:${cl.id}`,
          type: 'high_risk',
          severity: maxSeverity(...risky.map((t) => t.severity)),
          title: `Temat wysokiego ryzyka (${risky.map((t) => t.label.toLowerCase()).join(', ')}): ${cl.label}`,
          description:
            cl.noEvidenceRatio >= 0.5
              ? 'Brak potwierdzenia w źródłach — system wstrzymuje się od werdyktu. Wymagane pilne sprawdzenie przez wyznaczoną osobę.'
              : 'Zapytania dotyczą tematu wysokiego ryzyka. Werdykty są wydawane tylko na podstawie źródeł; zalecany przegląd przez wyznaczoną osobę.',
          rule: `Dopasowanie do tematu wysokiego ryzyka: ${risky.map((t) => `„${t.label}”`).join(', ')}${rules.highRisk.notifyImmediately ? ' — powiadomienie natychmiastowe' : ' — od 3 zapytań'}`,
          createdAt: recent.map((c) => c.createdAt).sort()[0],
          updatedAt: last(recent),
          clusterId: cl.id,
          checkIds: recent.map((c) => c.id),
          metrics: { 'Zapytania (24 h)': recent.length, 'Bez dowodów': pct(cl.noEvidenceRatio) },
        });
      }
    }
  }

  // Known incident and source status: context only, never a verdict.
  const flagged = (flag: CheckRecord['flags'][number]) =>
    checks.filter((c) => c.flags.includes(flag) && now - Date.parse(c.createdAt) <= 72 * HOUR);
  const incidentChecks = flagged('incident_match');
  for (const clusterId of new Set(incidentChecks.map((c) => c.clusterId ?? 'none'))) {
    const ids = incidentChecks.filter((c) => (c.clusterId ?? 'none') === clusterId);
    const cl = clusters.find((c) => c.id === clusterId);
    drafts.push({
      id: `incident_match:${clusterId}`,
      type: 'incident_match',
      severity: 'low',
      title: `Podobieństwo do znanego incydentu: ${cl?.label ?? 'zgłoszenia'}`,
      description:
        'Treść zgłoszeń jest podobna do przypadku z bazy incydentów (EUvsDisinfo). Dopasowanie jest pokazywane jako kontekst — nie jest podstawą werdyktu.',
      rule: 'Dopasowanie treści lub adresu do katalogu incydentów (72 h)',
      createdAt: ids.map((c) => c.createdAt).sort()[0],
      updatedAt: last(ids),
      clusterId: cl?.id,
      checkIds: ids.map((c) => c.id),
      metrics: { 'Zgłoszenia (72 h)': ids.length },
    });
  }

  const statusChecks = flagged('source_status_warning');
  if (statusChecks.length) {
    drafts.push({
      id: 'source_status:global',
      type: 'source_status',
      severity: 'low',
      title: 'Zgłoszenia z domeny o szczególnym statusie (sankcje UE)',
      description:
        'Użytkownicy przesyłają treści z domeny objętej sankcjami UE. Odpowiedzi zawierają neutralne ostrzeżenie o statusie źródła; status nie przesądza o prawdziwości treści.',
      rule: 'Domena zgłoszenia ma w katalogu status „wykluczone” z adnotacją o sankcjach',
      createdAt: statusChecks.map((c) => c.createdAt).sort()[0],
      updatedAt: last(statusChecks),
      checkIds: statusChecks.map((c) => c.id),
      metrics: { 'Zgłoszenia (72 h)': statusChecks.length },
    });
  }

  if (rules.promptInjection.enabled) {
    const injections = security.filter((e) => e.type === 'prompt_injection');
    // Busiest one-hour window in the last 24 h.
    let peak = 0;
    let peakAt = '';
    for (const e of injections) {
      const t = Date.parse(e.at);
      if (now - t > 24 * HOUR) continue;
      const n = injections.filter((x) => Math.abs(Date.parse(x.at) - t) <= HOUR / 2).length;
      if (n > peak) {
        peak = n;
        peakAt = e.at;
      }
    }
    if (peak >= rules.promptInjection.minEventsPerHour) {
      const recent = injections.filter((e) => now - Date.parse(e.at) <= 24 * HOUR);
      drafts.push({
        id: 'prompt_injection:global',
        type: 'prompt_injection',
        severity: peak >= 3 * rules.promptInjection.minEventsPerHour ? 'high' : 'medium',
        title: `Seria prób prompt injection (${recent.length} w 24 h)`,
        description:
          'Zgłoszenia lub pobrane strony zawierały polecenia dla modelu. Instrukcje zostały zignorowane, a zdarzenia zapisane w dzienniku bezpieczeństwa.',
        rule: `≥ ${rules.promptInjection.minEventsPerHour} prób w ciągu godziny`,
        createdAt: peakAt,
        updatedAt: last(recent),
        checkIds: recent.map((e) => e.checkId).filter((x): x is string => !!x),
        metrics: { 'Szczyt (1 h)': peak, 'Łącznie 24 h': recent.length, Odparte: '100%' },
      });
    }
  }

  const failures = checks.filter((c) => c.outcome === 'technical_error' && now - Date.parse(c.createdAt) <= 6 * HOUR);
  if (failures.length >= 3) {
    const reasons = [...new Set(failures.map((c) => c.errorMessage ?? 'Nieznany błąd'))];
    drafts.push({
      id: 'system:external-api',
      type: 'system',
      severity: failures.length >= 8 ? 'high' : 'medium',
      title: `Błędy techniczne zewnętrznych usług (${failures.length} w 6 h)`,
      description: `Zapytania zakończone awarią nie otrzymały werdyktu — użytkownik dostał komunikat o problemie technicznym. Przyczyny: ${reasons.join('; ')}.`,
      rule: '≥ 3 zapytania zakończone błędem technicznym w 6 h',
      createdAt: failures.map((c) => c.createdAt).sort()[0],
      updatedAt: last(failures),
      checkIds: failures.map((c) => c.id),
      metrics: { 'Błędy (6 h)': failures.length },
    });
  }

  return drafts;
}
