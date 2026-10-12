import { ApiError } from '@/services/http/errors'
import { apiGet, apiPost, type RequestOptions } from '@/services/http/client'
import { decodePage, isRecord, type SortBy, type AccountsTableResponse, type BrokersTableResponse, type PricesTableResponse, type SecuritiesTableResponse, type FxTableResponse } from '@/types/portfolioTables'

type Params = Record<string, unknown>
function withTotals<T>(value: unknown, label: string, key: string): T {
  const page = decodePage(value, label, key)
  if (!isRecord(page.totals)) throw new ApiError(`Invalid ${label} response`)
  return page as unknown as T
}
function isCount(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0
}
function isDisplay(value: unknown): value is string | null {
  return typeof value === 'string' || value === null
}
export function decodeAccountsTable(value: unknown): AccountsTableResponse {
  const page = withTotals<AccountsTableResponse>(value, 'accounts table', 'accounts')
  if (!page.accounts.every((row) =>
    isCount(row.id) && typeof row.name === 'string' &&
    typeof row.broker_name === 'string' && isCount(row.no_of_securities) &&
    typeof row.first_investment === 'string' && isDisplay(row.nav) &&
    isRecord(row.cash) && Object.values(row.cash).every(isDisplay) &&
    isDisplay(row.irr))) {
    throw new ApiError('Invalid accounts table response')
  }
  return page
}
export function decodeBrokersTable(value: unknown): BrokersTableResponse {
  const page = withTotals<BrokersTableResponse>(value, 'brokers table', 'items')
  if (!page.items.every((row) =>
    isCount(row.id) && typeof row.name === 'string' &&
    (typeof row.country === 'string' || row.country === null) &&
    isCount(row.no_of_accounts) && isCount(row.no_of_securities) &&
    typeof row.first_investment === 'string' && isDisplay(row.nav) &&
    isDisplay(row.cash) && isDisplay(row.irr))) {
    throw new ApiError('Invalid brokers table response')
  }
  return page
}
export function decodePricesTable(value: unknown): PricesTableResponse {
  const page = decodePage(value, 'prices table', 'prices') as unknown as PricesTableResponse
  if (!page.prices.every((row) =>
    isCount(row.id) && typeof row.date === 'string' &&
    typeof row.security__name === 'string' && typeof row.security__type === 'string' &&
    typeof row.security__currency === 'string' && isCount(row.security__id) &&
    isDisplay(row.price))) {
    throw new ApiError('Invalid prices table response')
  }
  return page
}
export function decodeSecuritiesTable(value: unknown): SecuritiesTableResponse {
  const page = decodePage(value, 'securities table', 'securities') as unknown as SecuritiesTableResponse
  if (!page.securities.every((row) =>
    isCount(row.id) && typeof row.type === 'string' &&
    (typeof row.ISIN === 'string' || row.ISIN === null) &&
    typeof row.name === 'string' && typeof row.first_investment === 'string' &&
    typeof row.currency === 'string' && isDisplay(row.open_position) &&
    isDisplay(row.current_value) && isDisplay(row.realized) &&
    isDisplay(row.unrealized) && isDisplay(row.capital_distribution) &&
    isDisplay(row.irr))) {
    throw new ApiError('Invalid securities table response')
  }
  return page
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
// The real backend wire (common/views.py get_year_options_api): numeric
// years as {text, value} strings, a {divider: true} separator, and the
// special ranges All-time/'ytd' — a mixed list, not an integer array.
export interface YearOption {
  text: string
  value: string
  divider?: boolean
}

export async function getYearOptions(options?: RequestOptions): Promise<YearOption[]> {
  const response = await apiGet('/api/get-year-options/', options)
  if (!isRecord(response) || !Array.isArray(response.table_years)) {
    throw new ApiError('Invalid year options response')
  }
  return response.table_years.map((entry) => {
    if (isRecord(entry) && entry.divider === true) {
      return { divider: true, text: '', value: '' }
    }
    if (isRecord(entry) && typeof entry.text === 'string' && typeof entry.value === 'string') {
      return { text: entry.text, value: entry.value }
    }
    throw new ApiError('Invalid year options response')
  })
}

/** Summary's breakdown selector: only the calendar years its endpoint takes. */
export function calendarYearOptions(options: YearOption[]): YearOption[] {
  return options
    .filter((option) => !option.divider && /^\d{4}$/.test(option.value))
    .map((option) => ({ text: option.text, value: option.value }))
}
