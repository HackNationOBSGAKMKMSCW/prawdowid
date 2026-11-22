import { getConfig } from '../config.ts';
import type { AdminApi } from './AdminApi.ts';
import { HttpAdminApi } from './http.ts';
import { MockAdminApi } from './mock/MockAdminApi.ts';
import type { Feature } from './types.ts';

export { ApiError } from './AdminApi.ts';
export type { AdminApi } from './AdminApi.ts';

let instance: AdminApi | null = null;

/**
 * The single data source used by the whole panel, chosen by
 * `config.dataSource`: `http` = the real admin API (`backend/admin`),
 * `mock` = example data in the browser. Pages do not change between them.
 */
export function getApi(): AdminApi {
  if (!instance) {
    const config = getConfig();
    instance = config.dataSource === 'http' ? new HttpAdminApi(config) : new MockAdminApi();
  }
  return instance;
}

/** Whether the current data source has an optional part of the panel. */
export function supports(feature: Feature): boolean {
  return getApi().capabilities.features.has(feature);
}
