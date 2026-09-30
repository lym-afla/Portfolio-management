import { ApiError } from '@/services/http/errors'

export type RawDecimalString = string & { readonly __rawDecimal: unique symbol }
export type DisplayString = string & { readonly __displayValue: unique symbol }
export type UnavailableValue = null | 'N/R'
export type DisplayValue = DisplayString | UnavailableValue
export type RecordCount = number

export interface SortBy {
  key?: string
  order?: 'asc' | 'desc' | boolean
  [key: string]: unknown
}

export interface PortfolioRow extends Record<string, unknown> {
  type: string; name: string; currency?: string
  current_position?: DisplayValue; investment_date?: string | null
  entry_price?: DisplayValue; entry_value?: DisplayValue
  current_price?: DisplayValue; current_value?: DisplayValue
  share_of_portfolio?: DisplayValue; price_change_percentage?: DisplayValue
  realized_gl?: DisplayValue; unrealized_gl?: DisplayValue
  capital_distribution?: DisplayValue; capital_distribution_percentage?: DisplayValue
  commission?: DisplayValue; commission_percentage?: DisplayValue
  total_return_amount?: DisplayValue; total_return_percentage?: DisplayValue
  exit_date?: string | null; exit_value?: DisplayValue
  irr?: DisplayValue
}
export interface TablePage {
  total_items: RecordCount
  current_page: number
  total_pages: number
}
export interface PortfolioTotals extends Record<string, unknown> {
  entry_value?: DisplayValue
  current_value?: DisplayValue
  realized_gl?: DisplayValue
  unrealized_gl?: DisplayValue
  capital_distribution?: DisplayValue
  commission?: DisplayValue
  total_return_amount?: DisplayValue
}
export interface OpenPositionsResponse extends TablePage {
  portfolio_open: PortfolioRow[]
  portfolio_open_totals: PortfolioTotals
  cash_balances: Record<string, DisplayValue>
}
export interface ClosedPositionsResponse extends TablePage {
  portfolio_closed: PortfolioRow[]
  portfolio_closed_totals: PortfolioTotals
  cash_balances: null
}
export interface TransactionRow extends Record<string, unknown> {
  id: string
  transaction_type: string
  date: string
  type: string
  cash_flow?: DisplayValue
  balances?: Record<string, DisplayValue>
}
export interface TransactionsResponse extends TablePage {
  transactions: TransactionRow[]
  currencies: string[]
}
export interface AccountRow extends Record<string, unknown> {
  id: number
  name: string
  broker_name: string
  no_of_securities: RecordCount
  first_investment: string
  nav: DisplayValue
  cash: Record<string, DisplayValue>
  irr: DisplayValue
}
export interface BrokerRow extends Record<string, unknown> {
  id: number
  name: string
  country: string | null
  no_of_accounts: RecordCount
  no_of_securities: RecordCount
  first_investment: string
  nav: DisplayValue
  cash: DisplayValue
  irr: DisplayValue
}
export interface PriceRow extends Record<string, unknown> {
  id: number
  date: string
  security__name: string
  security__type: string
  security__currency: string
  security__id: number
  price: DisplayValue
}
export interface SecurityRow extends Record<string, unknown> {
  id: number
  type: string
  ISIN: string | null
  name: string
  first_investment: string
  currency: string
  open_position: DisplayValue
  current_value: DisplayValue
  realized: DisplayValue
  unrealized: DisplayValue
  capital_distribution: DisplayValue
  irr: DisplayValue
}
export interface AccountsTableResponse extends TablePage {
  accounts: AccountRow[]
  totals: Record<string, unknown>
}
export interface BrokersTableResponse extends TablePage {
  items: BrokerRow[]
  totals: Record<string, unknown>
}
export interface PricesTableResponse extends TablePage {
  prices: PriceRow[]
}
export interface SecuritiesTableResponse extends TablePage {
  securities: SecurityRow[]
}
export interface FxRow extends Record<string, unknown> {
  id: number
  date: string | null
  from_currency: string
  to_currency: string
  rate: RawDecimalString
}
export interface FxTableResponse {
  results: FxRow[]
  count: RecordCount
  current_page: number
  total_pages: number
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
export function decodePage(value: unknown, label: string, rowKey: string, countKey = 'total_items'): Record<string, unknown> {
  if (!isRecord(value) || !Array.isArray(value[rowKey]) ||
      !value[rowKey].every(isRecord) ||
      !Number.isInteger(value[countKey]) || (value[countKey] as number) < 0 ||
      !Number.isInteger(value.current_page) || !Number.isInteger(value.total_pages)) {
    throw new ApiError(`Invalid ${label} response`)
  }
  return value
}
export function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new ApiError(`Invalid ${label} response`)
  return value
}
