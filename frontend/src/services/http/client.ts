import { ApiError, toApiError } from './errors'
import type { AxiosInstance, AxiosRequestConfig } from 'axios'

export interface RequestOptions { signal?: AbortSignal; sessionEpoch?: number }
function requestConfig(options?: RequestOptions): (AxiosRequestConfig & { _authEpoch?: number }) | undefined {
  if (!options?.signal && options?.sessionEpoch === undefined) return undefined
  return { ...(options.signal ? { signal: options.signal } : {}),
    ...(options.sessionEpoch !== undefined ? { _authEpoch: options.sessionEpoch } : {}) }
}

let readGuard: (() => boolean) | null = null
export function configurePortfolioReadGuard(guard: (() => boolean) | null): void { readGuard = guard }
function assertReadReady(url: string): void {
  // Context/auth endpoints must remain available during reconciliation. Only the
  // extracted read modules use this client for non-user endpoints.
  if (!url.startsWith('/users/') && readGuard && !readGuard()) throw new ApiError('Portfolio context is not ready', undefined, 'context_not_ready')
}
let installedClient: AxiosInstance | null = null
export function configureApiTransport(client: AxiosInstance | null): void { installedClient = client }
export function getApiTransport(): AxiosInstance {
  if (!installedClient) throw new Error('API transport is not initialized')
  return installedClient
}

export async function apiGet(url: string, options?: RequestOptions): Promise<unknown> {
  try { assertReadReady(url); return (await (requestConfig(options) ? getApiTransport().get(url, requestConfig(options)) : getApiTransport().get(url))).data }
  catch (error) { throw toApiError(error) }
}
export async function apiPost(url: string, body: unknown, options?: RequestOptions): Promise<unknown> {
  try { assertReadReady(url); return (await (requestConfig(options) ? getApiTransport().post(url, body, requestConfig(options)) : getApiTransport().post(url, body))).data }
  catch (error) { throw toApiError(error) }
}
