import { ApiError } from '@/services/http/errors'
import { apiGet, apiPost, type RequestOptions } from '@/services/http/client'
import { decodePage, isRecord, type SortBy, type AccountsTableResponse, type BrokersTableResponse, type PricesTableResponse, type SecuritiesTableResponse, type FxTableResponse } from '@/types/portfolioTables'

type Params = Record<string, unknown>
function withTotals<T>(value: unknown, label: string, key: string): T {
  const page = decodePage(value, label, key)
  if (!isRecord(page.totals)) throw new ApiError(`Invalid ${label} response`)
  return page as unknown as T
}
export function decodeAccountsTable(value: unknown): AccountsTableResponse {
  return withTotals<AccountsTableResponse>(value, 'accounts table', 'accounts')
}
export function decodeBrokersTable(value: unknown): BrokersTableResponse {
  return withTotals<BrokersTableResponse>(value, 'brokers table', 'items')
}
export function decodePricesTable(value: unknown): PricesTableResponse {
  return decodePage(value, 'prices table', 'prices') as unknown as PricesTableResponse
}
export function decodeSecuritiesTable(value: unknown): SecuritiesTableResponse {
  return decodePage(value, 'securities table', 'securities') as unknown as SecuritiesTableResponse
}
export function decodeFxTable(value: unknown): FxTableResponse {
  const page = decodePage(value, 'FX table', 'results', 'count')
  if (!(page.results as unknown[]).every((row) => isRecord(row) &&
      Number.isInteger(row.id) &&
      (typeof row.date === 'string' || row.date === null) &&
      typeof row.from_currency === 'string' &&
      typeof row.to_currency === 'string' &&
      typeof row.rate === 'string')) {
    throw new ApiError('Invalid FX table response')
  }
  return page as unknown as FxTableResponse
}
export async function getAccountsTable(params: Params = {}, options?: RequestOptions): Promise<AccountsTableResponse> {
  return decodeAccountsTable(await apiPost('/database/api/accounts/list_accounts/', params, options))
}
export async function getBrokersTable(params: Params = {}, options?: RequestOptions): Promise<BrokersTableResponse> {
  return decodeBrokersTable(await apiPost('/database/api/brokers/list_brokers/', params, options))
}
export async function getPrices(params: Params, options?: RequestOptions): Promise<PricesTableResponse> {
  return decodePricesTable(await apiPost('/database/api/get-prices-table/', params, options))
}
export async function getSecuritiesForDatabase(params: Params, options?: RequestOptions): Promise<SecuritiesTableResponse> {
  return decodeSecuritiesTable(await apiPost('/database/api/get-securities-for-database/', params, options))
}
export interface FxQuery {
  startDate: string; endDate: string; page: number; itemsPerPage: number
  sortBy: SortBy; search: string
}
export async function getFXData(query: FxQuery, options?: RequestOptions): Promise<FxTableResponse> {
  const { startDate, endDate, page, itemsPerPage, sortBy, search } = query
  return decodeFxTable(await apiPost('/database/api/fx/list_fx/',
    { startDate, endDate, page, itemsPerPage, sortBy, search }, options))
}
export async function getYearOptions(options?: RequestOptions): Promise<number[]> {
  const response = await apiGet('/api/get-year-options/', options)
  if (!isRecord(response) || !Array.isArray(response.table_years) ||
      !response.table_years.every((year) => Number.isInteger(year))) {
    throw new ApiError('Invalid year options response')
  }
  return response.table_years as number[]
}
