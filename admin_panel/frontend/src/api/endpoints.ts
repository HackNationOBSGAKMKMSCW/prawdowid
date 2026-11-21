/**
 * Paths of the admin API, relative to `apiBaseUrl`. Every key can be
 * overridden in `public/config.json` → `endpoints`, so the panel can follow
 * a backend whose routes differ without touching the code. `:name` segments
 * are filled in by `buildPath`.
 *
 * The contract for these routes is in `admin_panel/openapi.yaml`.
 */
export const DEFAULT_ENDPOINTS = {
  login: '/auth/login',
  logout: '/auth/logout',
  me: '/auth/me',
  health: '/health',
  dashboard: '/dashboard',
  alerts: '/alerts',
  alert: '/alerts/:id',
  alertEscalate: '/alerts/:id/escalate',
  clusters: '/clusters',
  cluster: '/clusters/:id',
  cases: '/cases',
  case: '/cases/:id',
  caseComments: '/cases/:id/comments',
  caseForward: '/cases/:id/forward',
  checks: '/checks',
  check: '/checks/:id',
  sources: '/sources',
  source: '/sources/:id',
  sourceRefresh: '/sources/:id/refresh',
  providers: '/models/providers',
  provider: '/models/providers/:id',
  providerTest: '/models/providers/:id/test',
  assignments: '/models/assignments',
  assignment: '/models/assignments/:role',
  channels: '/channels',
  channel: '/channels/:id',
  securityEvents: '/security/events',
  alertRules: '/settings/alert-rules',
  privacy: '/settings/privacy',
  purgeDemo: '/settings/privacy/purge-demo',
  users: '/users',
  user: '/users/:id',
  audit: '/audit',
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
