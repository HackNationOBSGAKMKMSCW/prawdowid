import { mockCheck, type Scenario } from './mock.ts';
import type { CheckResponse } from './types.ts';

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
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      Accept: 'application/json',
      ...init?.headers,
    },
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
const configuredTimeout = Number(import.meta.env.VITE_CHECK_TIMEOUT_MS || 360_000);
const CHECK_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout > 0
  ? configuredTimeout
  : 360_000;

function withTimeout(signal: AbortSignal | undefined, ms: number): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

/** Sprawdza wiadomość albo link. */
export function checkMessage(text: string, options: CheckOptions = {}): Promise<CheckResponse> {
  if (options.scenario || API_MODE === 'mock') {
    return mockCheck(text, options.scenario, options.signal);
  }
  const query = new URLSearchParams({ text });
  return request<CheckResponse>(`/check?${query.toString()}`, {
    method: 'GET',
    signal: withTimeout(options.signal, CHECK_TIMEOUT_MS),
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
