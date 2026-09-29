import { toApiError } from './errors'
import type { AxiosInstance } from 'axios'

export interface RequestOptions { signal?: AbortSignal }

let installedClient: AxiosInstance | null = null
export function configureApiTransport(client: AxiosInstance | null): void { installedClient = client }
export function getApiTransport(): AxiosInstance {
  if (!installedClient) throw new Error('API transport is not initialized')
  return installedClient
}

export async function apiGet(url: string, options?: RequestOptions): Promise<unknown> {
  try { return (await (options?.signal ? getApiTransport().get(url, { signal: options.signal }) : getApiTransport().get(url))).data }
  catch (error) { throw toApiError(error) }
}
export async function apiPost(url: string, body: unknown, options?: RequestOptions): Promise<unknown> {
  try { return (await (options?.signal ? getApiTransport().post(url, body, { signal: options.signal }) : getApiTransport().post(url, body))).data }
  catch (error) { throw toApiError(error) }
}
