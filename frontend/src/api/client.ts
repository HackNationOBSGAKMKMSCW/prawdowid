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

/** Sprawdza wiadomość albo link. */
export function checkMessage(text: string, options: CheckOptions = {}): Promise<CheckResponse> {
  if (options.scenario || API_MODE === 'mock') {
    return mockCheck(text, options.scenario, options.signal);
  }
  return request<CheckResponse>('/check', {
    method: 'POST',
    body: JSON.stringify({ text }),
    signal: options.signal,
  });
}

function isDemoId(id?: string): boolean {
  return !id || id.startsWith('demo-') || API_MODE === 'mock';
}

/** Zgłasza błędny wynik do przejrzenia przez zespół. */
export async function reportCheck(id?: string): Promise<void> {
  if (isDemoId(id)) return;
  await request<void>(`/check/${encodeURIComponent(id!)}/report`, { method: 'POST', body: '{}' });
}

/** Usuwa zapisaną wiadomość użytkownika. */
export async function deleteCheck(id?: string): Promise<void> {
  if (isDemoId(id)) return;
  await request<void>(`/check/${encodeURIComponent(id!)}`, { method: 'DELETE' });
}
