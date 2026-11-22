import { mockCheck, type Scenario } from './mock.ts';
import type { CheckResponse } from './types.ts';

/**
 * `mock` – odpowiedzi przykładowe, bez backendu (domyślnie).
 * `live` – zapytania do `/api` (w dev Vite przekierowuje je na 127.0.0.1:8000).
 */
export const API_MODE: 'mock' | 'live' = import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

/**
 * Kody błędów backendu (`backend/API.md`) oraz dwa po stronie przeglądarki:
 * `network` (brak połączenia) i `timeout` (przekroczony VITE_CHECK_TIMEOUT_MS).
 */
export type ApiErrorCode =
  | 'invalid_request'
  | 'invalid_url'
  | 'unsafe_url'
  | 'url_unavailable'
  | 'request_too_large'
  | 'result_not_found'
  | 'analysis_failed'
  | 'invalid_analysis_result'
  | 'analysis_busy'
  // odmowa monitora panelu admina (backend/admin/web.py)
  | 'request_refused'
  | 'user_blocked'
  // konta (/api/auth): zły e-mail lub hasło, wygasła sesja, za dużo prób logowania
  | 'unauthorized'
  | 'forbidden'
  | 'too_many_attempts'
  | 'storage_unavailable'
  | 'analysis_timeout'
  | 'internal_error'
  | 'network'
  | 'timeout'
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  /** `X-Request-ID` z odpowiedzi — do zgłoszenia problemu. */
  readonly requestId?: string;

  constructor(status: number, code: ApiErrorCode, message: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const STATUS_CODES: Partial<Record<number, ApiErrorCode>> = {
  401: 'unauthorized',
  403: 'forbidden',
  422: 'invalid_request',
  429: 'too_many_attempts',
};

/** Komunikat z `{"detail": "..."}` albo z listy błędów walidacji FastAPI. */
function detailMessage(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : ''))
      .filter(Boolean);
    return messages.join(' ') || undefined;
  }
  return undefined;
}

/**
 * Odpowiedź błędu backendu: `{ "error": { "code", "message" }, "request_id" }`, a dla kont
 * (`/api/auth`) `{ "detail": ... }` z komunikatem po polsku.
 */
async function errorFrom(res: Response): Promise<ApiError> {
  let code: ApiErrorCode = 'unknown';
  let message = `${res.status} ${res.statusText}`;
  let requestId = res.headers.get('X-Request-ID') ?? undefined;
  try {
    const body = (await res.json()) as {
      error?: { code?: string; message?: string };
      request_id?: string;
      detail?: unknown;
    };
    if (body.error?.code) code = body.error.code as ApiErrorCode;
    if (body.error?.message) message = body.error.message;
    const detail = detailMessage(body.detail);
    if (detail) {
      message = detail;
      code = STATUS_CODES[res.status] ?? code;
    }
    requestId = body.request_id ?? requestId;
  } catch {
    // Brak JSON (np. 502 z proxy) — zostaje status HTTP.
  }
  return new ApiError(res.status, code, message, requestId);
}

/** Token sesji zalogowanego użytkownika; dołączany do każdego zapytania (`Authorization`). */
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        Accept: 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...init?.headers,
      },
    });
  } catch (err) {
    const name = (err as Error).name;
    if (name === 'TimeoutError') throw new ApiError(0, 'timeout', 'Przekroczono czas oczekiwania.');
    if (name === 'AbortError') throw err;
    throw new ApiError(0, 'network', 'Brak połączenia z serwerem.');
  }
  if (!res.ok) throw await errorFrom(res);
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

/** Limit `text` w `GET /api/check` (backend: `max_length=20_000`). */
export const MAX_TEXT_LENGTH = 20_000;

/** Sprawdza wiadomość albo link. */
export function checkMessage(text: string, options: CheckOptions = {}): Promise<CheckResponse> {
  if (options.scenario || API_MODE === 'mock') {
    return mockCheck(text, options.scenario, options.signal);
  }
  if (text.length > MAX_TEXT_LENGTH) {
    return Promise.reject(new ApiError(422, 'request_too_large', 'Wiadomość jest za długa.'));
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

// ── stan backendu i lista źródeł ────────────────────────────────────────────

/**
 * `GET /api/health`: czy API strony działa (razem z bazą). W trybie mock zawsze `true`.
 * Nie rzuca wyjątku — zwraca `false`, gdy serwer nie odpowiada.
 */
export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  if (API_MODE === 'mock') return true;
  try {
    const body = await request<{ status?: string }>('/health', {
      signal: withTimeout(signal, 5_000),
    });
    return body?.status === 'ok';
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    return false;
  }
}

/** Źródło zaufane z `GET /api/trusted-sources` (tylko pola publiczne). */
export interface TrustedSource {
  id: string;
  name: string;
  url: string;
  /** `official` – urzędowe, `fact_checker` – serwisy sprawdzające fakty, `other` – pozostałe. */
  trust: 'official' | 'fact_checker' | 'other' | (string & {});
  topics: string[];
  description: string;
}

/** Lista źródeł, z których korzysta weryfikacja. W trybie mock `null` (strona pokaże listę z kodu). */
export async function listTrustedSources(signal?: AbortSignal): Promise<TrustedSource[] | null> {
  if (API_MODE === 'mock') return null;
  return request<TrustedSource[]>('/trusted-sources', { signal: withTimeout(signal, 10_000) });
}

// ── konta użytkowników strony (/api/auth) ───────────────────────────────────

/** Konta działają tylko z prawdziwym API (tryb `live`). */
export const ACCOUNTS_ENABLED = API_MODE !== 'mock';

export interface Account {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface AccountSession {
  token: string;
  user: Account;
  /** Kiedy sesja wygasa (ISO 8601); `null` = bez terminu. */
  expiresAt: string | null;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
}

export function signIn(email: string, password: string): Promise<AccountSession> {
  return postJson<AccountSession>('/auth/login', { email, password });
}

export function signUp(name: string, email: string, password: string): Promise<AccountSession> {
  return postJson<AccountSession>('/auth/register', { name, email, password });
}

/** Unieważnia token na serwerze. Błąd (np. sesja już wygasła) nie przeszkadza w wylogowaniu. */
export async function signOut(): Promise<void> {
  try {
    await request<void>('/auth/logout', { method: 'POST', signal: AbortSignal.timeout(10_000) });
  } catch {
    // Token i tak zostaje usunięty z przeglądarki.
  }
}

export function fetchAccount(signal?: AbortSignal): Promise<Account> {
  return request<Account>('/auth/me', { signal: withTimeout(signal, 10_000) });
}

export async function changePassword(current: string, next: string): Promise<void> {
  await postJson<void>('/auth/me/password', { current, new: next });
}

/** Wpis z historii sprawdzeń zalogowanego użytkownika (`GET /api/auth/me/queries`). */
export interface AccountCheck {
  id: string;
  ts: string;
  channel: string | null;
  text: string | null;
  /** `w_toku`, `zakonczone`, `odrzucone`, `blad`. */
  status: string;
  /** Werdykt całości w słowniku dziennika (np. `falsz`, `prawda`). */
  verdict: string | null;
  flags: string[] | null;
  completed_at: string | null;
}

export function listMyChecks(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<{ total: number; items: AccountCheck[] }> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request(`/auth/me/queries?${query.toString()}`, { signal: withTimeout(signal, 10_000) });
}
