/**
 * Runtime configuration of the admin panel.
 *
 * Nothing about the backend is hard-coded in the components. Values are
 * resolved in this order (later wins):
 *   1. built-in defaults below,
 *   2. build-time env (`VITE_ADMIN_DATA_SOURCE`, `VITE_ADMIN_API_URL`),
 *   3. `public/config.json`, fetched at start-up, so an operator can point a
 *      built panel at another API (or another set of paths) without a rebuild.
 */
import { DEFAULT_ENDPOINTS, type EndpointMap } from './api/endpoints.ts';

export type DataSource = 'mock' | 'http';

export interface AdminConfig {
  /** `http` = real admin API (`backend/admin`), `mock` = example data generated in the browser. */
  dataSource: DataSource;
  /** Absolute URL or a path relative to the panel's origin, e.g. `/api/admin`. */
  apiBaseUrl: string;
  requestTimeoutMs: number;
  /** Shown in the top bar, e.g. "demo", "pilotaż", "produkcja". */
  environmentLabel: string;
  /** Per-endpoint path overrides; see `api/endpoints.ts` for the keys. */
  endpoints: EndpointMap;
}

const DEFAULTS: AdminConfig = {
  dataSource: 'http',
  apiBaseUrl: '/api/admin',
  requestTimeoutMs: 20_000,
  environmentLabel: 'backend',
  endpoints: DEFAULT_ENDPOINTS,
};

let current: AdminConfig = DEFAULTS;

function fromEnv(): Partial<AdminConfig> {
  const env = import.meta.env;
  const partial: Partial<AdminConfig> = {};
  if (env.VITE_ADMIN_DATA_SOURCE === 'mock' || env.VITE_ADMIN_DATA_SOURCE === 'http') {
    partial.dataSource = env.VITE_ADMIN_DATA_SOURCE;
  }
  if (typeof env.VITE_ADMIN_API_URL === 'string' && env.VITE_ADMIN_API_URL.trim()) {
    partial.apiBaseUrl = env.VITE_ADMIN_API_URL.trim();
  }
  return partial;
}

function sanitize(raw: unknown): Partial<AdminConfig> {
  if (!raw || typeof raw !== 'object') return {};
  const r = raw as Record<string, unknown>;
  const out: Partial<AdminConfig> = {};
  if (r.dataSource === 'mock' || r.dataSource === 'http') out.dataSource = r.dataSource;
  if (typeof r.apiBaseUrl === 'string' && r.apiBaseUrl.trim()) out.apiBaseUrl = r.apiBaseUrl.trim();
  if (typeof r.requestTimeoutMs === 'number' && r.requestTimeoutMs > 0) {
    out.requestTimeoutMs = r.requestTimeoutMs;
  }
  if (typeof r.environmentLabel === 'string') out.environmentLabel = r.environmentLabel;
  if (r.endpoints && typeof r.endpoints === 'object') {
    const overrides: Partial<EndpointMap> = {};
    for (const [key, value] of Object.entries(r.endpoints as Record<string, unknown>)) {
      if (key in DEFAULT_ENDPOINTS && typeof value === 'string' && value.startsWith('/')) {
        overrides[key as keyof EndpointMap] = value;
      }
    }
    out.endpoints = { ...DEFAULT_ENDPOINTS, ...overrides };
  }
  return out;
}

/** Load `config.json` once before the app renders. A missing file is not an error. */
export async function loadConfig(): Promise<AdminConfig> {
  let fileConfig: Partial<AdminConfig> = {};
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}config.json`, { cache: 'no-store' });
    if (res.ok) fileConfig = sanitize(await res.json());
  } catch {
    // No runtime config: build-time env and defaults apply.
  }
  current = { ...DEFAULTS, ...fromEnv(), ...fileConfig };
  return current;
}

export function getConfig(): AdminConfig {
  return current;
}
