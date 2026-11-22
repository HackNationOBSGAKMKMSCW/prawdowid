/**
 * Paths of the admin API (`backend/admin/api.py`), relative to `apiBaseUrl`
 * (by default `/api/admin`). Every key can be overridden in
 * `public/config.json` → `endpoints`, so the panel can follow a backend whose
 * routes differ without touching the code. `:name` segments are filled in by
 * `buildPath`.
 */
export const DEFAULT_ENDPOINTS = {
  health: '/health',
  login: '/auth/login',
  logout: '/auth/logout',
  me: '/auth/me',
  ownPassword: '/auth/me/password',
  accounts: '/accounts',
  account: '/accounts/:id',
  accountPassword: '/accounts/:id/password',
  dashboard: '/dashboard',
  queries: '/queries',
  query: '/queries/:id',
  events: '/events',
  eventsSummary: '/events/summary',
  alerts: '/alerts',
  alert: '/alerts/:id',
  infoGaps: '/info-gaps',
  infoGap: '/info-gaps/:id',
  topic: '/topics/:id',
  config: '/config',
  configAudit: '/config/audit',
  activity: '/activity',
  configModels: '/config/models',
  purge: '/maintenance/purge',
  sources: '/sources',
  ipBlocks: '/ip-blocks',
  ipBlock: '/ip-blocks/:key/block',
  ipUnblock: '/ip-blocks/:key/unblock',
  sourcesStatus: '/sources/status',
  sourcesCheck: '/sources/check',
  threats: '/threats',
} as const;

export type EndpointKey = keyof typeof DEFAULT_ENDPOINTS;
export type EndpointMap = Record<EndpointKey, string>;

export function buildPath(
  endpoints: EndpointMap,
  key: EndpointKey,
  params: Record<string, string> = {},
): string {
  return endpoints[key].replace(/:([a-zA-Z_]+)/g, (_, name: string) => {
    const value = params[name];
    if (value === undefined) throw new Error(`Brak parametru "${name}" dla ścieżki ${key}`);
    return encodeURIComponent(value);
  });
}
