import { getConfig } from '../config.ts';
import type { AdminApi } from './AdminApi.ts';
import { HttpAdminApi } from './http.ts';
import { MockAdminApi } from './mock/MockAdminApi.ts';

export { ApiError } from './AdminApi.ts';
export type { AdminApi } from './AdminApi.ts';

let instance: AdminApi | null = null;

/**
 * The single data source used by the whole panel, chosen by
 * `config.dataSource`. To plug in another backend, implement `AdminApi`
 * and return it here — pages do not change.
 */
export function getApi(): AdminApi {
  if (!instance) {
    const config = getConfig();
    instance = config.dataSource === 'http' ? new HttpAdminApi(config) : new MockAdminApi();
  }
  return instance;
}
