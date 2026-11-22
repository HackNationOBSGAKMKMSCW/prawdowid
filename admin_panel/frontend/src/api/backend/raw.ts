/**
 * Response shapes of `backend/admin` (store.py rows, api.py payloads), as they
 * arrive over the wire. Only `mappers.ts` reads them; pages use `types.ts`.
 */

export interface RawSafety {
  severity: 'brak' | 'sredni' | 'wysoki';
  categories: string[];
  operational_intent: boolean;
  matches: string[];
}

export interface RawClaim {
  id?: number;
  query_id?: string;
  ts?: string;
  topic_id?: string;
  text: string;
  verdict: string | null;
  /** `prawda` | `falsz` | `luka` | `inne` */
  kind: string;
  sources_count: number | null;
}

export interface RawQuery {
  id: string;
  ts: string;
  channel: string | null;
  text: string | null;
  status: 'w_toku' | 'zakonczone' | 'odrzucone' | 'blad' | string;
  verdict: string | null;
  flags: string[] | null;
  safety: RawSafety | null;
  request_id: string | null;
  sources_count: number | null;
  completed_at: string | null;
  error: string | null;
  /** Mistake reported from the website (`POST /api/check/{id}/report`). */
  report?: { reason: string; comment: string | null; ts: string | null } | null;
  /** Only in `GET /queries/{id}`. */
  claims?: RawClaim[];
}

/** Row of `trusted_sources` (`GET /sources`). */
export interface RawTrustedSource {
  url: string;
  name: string;
  topics: string[] | null;
  description: string | null;
  adapter: string | null;
  params: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** The same site as the running verification sees it (`GET /sources/status`). */
export interface RawSourceStatus {
  id: string;
  url: string;
  name: string;
  adapter: string;
  trust: string;
  enabled: boolean;
  domains: string[];
  last_check: { at: string; ok: boolean; error: string | null } | null;
}

export interface RawQueryPage {
  total: number;
  limit: number;
  offset: number;
  items: RawQuery[];
}

export interface RawAlert {
  id: string;
  type: 'luka_informacyjna' | 'kampania_dezinformacyjna' | 'tresci_niebezpieczne' | 'prompt_injection' | 'rosyjska_dezinformacja' | 'sql_injection' | string;
  subject: string;
  severity: string;
  status: 'otwarty' | 'w_analizie' | 'rozwiazany' | 'falszywy_alarm' | string;
  title: string;
  count: number;
  users: number;
  first_seen: string;
  last_seen: string;
  details: Record<string, unknown>;
  note: string | null;
  updated_at: string;
}

export interface RawGap {
  id: string;
  label: string;
  created_at: string;
  last_seen: string;
  gap_status: string;
  gap_since: string | null;
  gap_users: number;
  gap_queries?: number;
  gap_note: string | null;
  gap_updated_at: string | null;
}

export interface RawTopic extends RawGap {
  tokens: string[];
  claims: RawClaim[];
  by_kind: Record<string, { claims: number; users: number }>;
}

export interface RawDashboard {
  generated_at: string;
  window_hours: number;
  queries: number;
  dangerous_queries: number;
  verdicts: Record<string, number>;
  statuses: Record<string, number>;
  open_alerts: Record<string, number>;
  active_info_gaps: number;
  latest_alerts: RawAlert[];
}

export interface RawSecretState {
  nadpisany: boolean;
  ustawiony: boolean;
  maska: string | null;
}

export interface RawConfig {
  llm: import('../types.ts').LlmSettings;
  apis: import('../types.ts').ApiSettings;
  monitoring: import('../types.ts').MonitoringSettings;
  secrets: Record<string, RawSecretState>;
  efektywne: Record<string, string | null>;
  api_clients?: string[];
  gap_statuses?: string[];
  file?: string;
}

export interface RawAudit {
  id: number;
  ts: string;
  actor: string;
  field: string;
  old: unknown;
  new: unknown;
}

export interface RawEvent {
  ts?: string;
  level?: string;
  event?: string;
  request_id?: string;
  [key: string]: unknown;
}

/** `User.public()` from backend/accounts — already in the panel's shape. */
export interface RawAccount {
  id: string | number;
  email: string;
  name: string;
  role: 'admin' | 'analyst' | 'user';
  active: boolean;
  createdAt: string;
  lastLoginAt: string | null;
}

/** A row of `activity_logs` (`GET /activity`). */
export interface RawActivity {
  id: number;
  occurred_at: string;
  user_id: number | null;
  actor: string;
  action: string;
  subject_type: string | null;
  subject_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
}
