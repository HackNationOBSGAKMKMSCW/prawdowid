import { mockCheck, type Scenario } from './mock.ts';
import { mockClarify } from './mockClarify.ts';
import type { CheckResponse, ClarifyStep, ClarifyTurn } from './types.ts';

/**
 * `mock` – odpowiedzi przykładowe, bez backendu (domyślnie).
 * `live` – zapytania do `/api` (w dev Vite przekierowuje je na 127.0.0.1:8000).
 */
export const API_MODE: 'mock' | 'live' = import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
  });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CheckOptions {
  signal?: AbortSignal;
  /** Wymusza przykładowy scenariusz (pasek demo). Zawsze używa danych przykładowych. */
  scenario?: Scenario;
}

/** Po tym czasie sprawdzenie kończy się ekranem „Coś poszło nie tak”. */
const CHECK_TIMEOUT_MS = 90_000;

function withTimeout(signal: AbortSignal | undefined, ms: number): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

/** Sprawdza wiadomość albo link. */
export function checkMessage(text: string, options: CheckOptions = {}): Promise<CheckResponse> {
  if (options.scenario || API_MODE === 'mock') {
    return mockCheck(text, options.scenario, options.signal);
  }
  return request<CheckResponse>('/check', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal: withTimeout(options.signal, CHECK_TIMEOUT_MS),
  });
}

/** Dopytanie jest dodatkiem: po tym czasie sprawdzamy to, co już wiemy. */
const CLARIFY_TIMEOUT_MS = 25_000;

/**
 * Krok pętli doprecyzowania: czy dopytać o szczegóły (kiedy, gdzie…), czy już sprawdzać.
 * Rozmowa żyje w przeglądarce, serwer niczego nie przechowuje.
 */
export function clarifyMessage(
  turns: ClarifyTurn[],
  options: { signal?: AbortSignal } = {},
): Promise<ClarifyStep> {
  if (API_MODE === 'mock') return mockClarify(turns, options.signal);
  return request<ClarifyStep>('/clarify', {
    method: 'POST',
    body: JSON.stringify({ turns }),
    signal: withTimeout(options.signal, CLARIFY_TIMEOUT_MS),
  });
}

function isDemoId(id?: string): boolean {
  return !id || id.startsWith('demo-') || API_MODE === 'mock';
}

export type ReportReason = 'wrong_verdict' | 'bad_source' | 'misunderstood' | 'other';

export interface ReportPayload {
  reason: ReportReason;
  comment?: string;
}

/** Zgłasza błędny wynik do przejrzenia przez zespół. */
export async function reportCheck(id: string | undefined, report: ReportPayload): Promise<void> {
  if (isDemoId(id)) {
    await new Promise((resolve) => window.setTimeout(resolve, 600));
    return;
  }
  await request<void>(`/check/${encodeURIComponent(id!)}/report`, {
    method: 'POST',
    body: JSON.stringify(report),
  });
}
