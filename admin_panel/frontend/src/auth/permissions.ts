import type { Role, User } from '../api/types.ts';

export type Permission =
  | 'dashboard:read'
  | 'alerts:read'
  | 'alerts:write'
  | 'clusters:read'
  | 'cases:read'
  | 'cases:write'
  | 'cases:forward'
  | 'checks:read'
  | 'checks:delete'
  | 'sources:read'
  | 'sources:write'
  | 'models:read'
  | 'models:write'
  | 'channels:write'
  | 'security:read'
  | 'rules:read'
  | 'rules:write'
  | 'settings:read'
  | 'settings:write'
  | 'users:read'
  | 'users:write'
  | 'audit:read'
  | 'endusers:read'
  | 'endusers:write'
  | 'export';

/** Observation panel: everything read-only, plus export. */
const OBSERVE: Permission[] = [
  'dashboard:read',
  'alerts:read',
  'clusters:read',
  'cases:read',
  'checks:read',
  'sources:read',
  'security:read',
  'rules:read',
  'endusers:read',
  'export',
];

const COMMON: Permission[] = [...OBSERVE, 'alerts:write', 'cases:write', 'cases:forward'];

/**
 * Role → permissions. The backend enforces the same rules; the panel uses
 * them only to hide what a user cannot do.
 */
export const ROLE_PERMISSIONS: Record<Role, ReadonlySet<Permission>> = {
  admin: new Set<Permission>([
    ...COMMON,
    'checks:delete',
    'sources:write',
    'models:read',
    'models:write',
    'channels:write',
    'rules:write',
    'settings:read',
    'settings:write',
    'users:read',
    'users:write',
    'audit:read',
    'endusers:write',
  ]),
  // Read-only observer; the administrator creates and manages the account.
  analyst: new Set<Permission>([...OBSERVE, 'models:read', 'settings:read']),
  // Accounts of the public service cannot use the panel (the backend refuses them too).
  user: new Set<Permission>(),
};

export function can(user: Pick<User, 'role'> | null | undefined, permission: Permission): boolean {
  return !!user && ROLE_PERMISSIONS[user.role].has(permission);
}
