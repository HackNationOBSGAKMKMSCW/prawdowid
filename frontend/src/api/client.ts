import { mockCheck, type Scenario } from './mock.ts';
import type { CheckResponse, LlmInputResponse, MaskingResponse } from './types.ts';

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

/**
 * Maskuje dane osobowe (poza imieniem i nazwiskiem) w backendzie.
 * Zawsze pyta prawdziwy backend, także w trybie `mock`: to narzędzie do testowania reguł.
 */
export function maskText(text: string, signal?: AbortSignal): Promise<MaskingResponse> {
  return request<MaskingResponse>('/masking', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal: withTimeout(signal, 15_000),
  });
}

/**
 * Okno „Do LLM trafi” po kliknięciu „Sprawdź”. Domyślnie włączone w `npm run dev`,
 * w buildzie produkcyjnym tylko z `VITE_SHOW_LLM_INPUT=true`.
 */
export const SHOW_LLM_INPUT =
  import.meta.env.VITE_SHOW_LLM_INPUT === 'true' ||
  (import.meta.env.DEV && import.meta.env.VITE_SHOW_LLM_INPUT !== 'false');

/** Tekst, który backend wyśle do LLM (nic nie trafia do modelu). Zawsze pyta prawdziwy backend. */
export function previewLlmInput(text: string, signal?: AbortSignal): Promise<LlmInputResponse> {
  return request<LlmInputResponse>('/masking/llm-input', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal: withTimeout(signal, 15_000),
  });
}
