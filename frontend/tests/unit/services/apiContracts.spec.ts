import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosInstance } from 'axios'
import { configureApiTransport, getApiTransport } from '@/services/http/client'
import { decodeOpenPositions, decodeClosedPositions, getOpenPositions } from '@/services/api/portfolio'
import { decodeDashboardSummary } from '@/services/api/dashboard'
import { decodeTransactions, getTransactions } from '@/services/api/transactions'
import { decodeFxTable, decodeAccountsTable, decodeBrokersTable, decodePricesTable, decodeSecuritiesTable, getFXData, getYearOptions } from '@/services/api/database'
import { configurePortfolioContextBackend, getPortfolioContextBackend, createPortfolioContextBackend } from '@/services/api/context'

const http = { get: vi.fn(), post: vi.fn() }
beforeEach(() => {
  configureApiTransport(http as unknown as AxiosInstance)
  http.get.mockReset()
  http.post.mockReset()
})
afterEach(() => {
  configureApiTransport(null)
  configurePortfolioContextBackend(null)
})
describe('typed API transport', () => {
  it('forwards the legacy open positions body and cancellation', async () => {
    const controller = new AbortController()
    const payload = { portfolio_open: [], portfolio_open_totals: {}, cash_balances: {}, total_items: 0, current_page: 1, total_pages: 1 }
    http.post.mockResolvedValue({ data: payload })
    expect(await getOpenPositions(null, '2025-12-31', 1, 25, '', {}, { signal: controller.signal })).toEqual(payload)
    expect(http.post).toHaveBeenCalledWith('/open_positions/api/get_open_positions_table/',
      { dateFrom: null, dateTo: '2025-12-31', page: 1, itemsPerPage: 25, search: '', sortBy: {} },
      expect.objectContaining({ signal: controller.signal }))
  })
  it('rejects malformed table rows instead of presenting an empty portfolio', () => {
    expect(() => decodeOpenPositions({ total_items: 1 })).toThrow('Invalid open positions response')
  })
  it('preserves direct dashboard metrics and unavailable values', () => {
    const payload = { 'Current NAV': '1,234.50', Invested: '900.00', 'Cash-out': '100.00', total_return: null, irr: null }
    expect(decodeDashboardSummary(payload)).toEqual(payload)
    expect(() => decodeDashboardSummary({ metrics: payload })).toThrow('Invalid dashboard summary response')
  })
  it('keeps the installed client and context backend independently resettable', () => {
    expect(getApiTransport()).toBe(http)
    configureApiTransport(null)
    expect(() => getApiTransport()).toThrow('API transport is not initialized')
    const backend = createPortfolioContextBackend(async () => undefined)
    configurePortfolioContextBackend(backend)
    expect(getPortfolioContextBackend()).toBe(backend)
    configurePortfolioContextBackend(null)
    expect(() => getPortfolioContextBackend()).toThrow('Portfolio context backend is not initialized')
  })
  it('uses dashboard settings names and awaits effective-date refresh', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined)
    const backend = createPortfolioContextBackend(refresh)
    http.post.mockResolvedValue({ data: { requires_token_refresh: true, new_effective_date: '2025-12-31' } })
    http.get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('user_settings')
      ? { selected_account_type: 'all', selected_account_id: null }
      : { settings: { table_date: '2025-12-31', default_currency: 'USD', digits: 2 }, choices: {} } }))
    await backend.updateSettings({ effectiveCurrentDate: '2025-12-31', currency: 'USD', digits: 2 })
    expect(http.post).toHaveBeenCalledWith('/users/api/update_dashboard_settings/',
      { table_date: '2025-12-31', default_currency: 'USD', digits: 2 })
    expect(refresh).toHaveBeenCalledWith('2025-12-31')
    expect(await backend.read()).toEqual({ accountSelection: { type: 'all', id: null }, effectiveCurrentDate: '2025-12-31', currency: 'USD', digits: 2 })
  })
  it('normalizes transport failures without exposing request configuration', async () => {
    http.post.mockRejectedValue({ response: { status: 422, data: { code: 'invalid', field: ['required'], headers: { Authorization: 'secret' } } }, config: { headers: { Authorization: 'secret' } } })
    await expect(getOpenPositions(null, null, 1, 25)).rejects.toMatchObject({ name: 'ApiError', status: 422, code: 'invalid', details: { field: ['required'] } })
  })
  it('preserves formatted position values and rejects incomplete rows', () => {
    const page = { total_items: 1, current_page: 1, total_pages: 1 }
    const row = { name: 'Bond', type: 'Bond', current_value: '1,234.50', irr: null }
    expect(decodeOpenPositions({ ...page, portfolio_open: [row], portfolio_open_totals: { current_value: '1,234.50' }, cash_balances: { USD: '10.00' } }).portfolio_open[0].current_value).toBe('1,234.50')
    expect(decodeClosedPositions({ ...page, portfolio_closed: [row], portfolio_closed_totals: {}, cash_balances: null }).portfolio_closed).toEqual([row])
    expect(() => decodeOpenPositions({ ...page, portfolio_open: [{}], portfolio_open_totals: {}, cash_balances: {} })).toThrow('Invalid open positions response')
    expect(() => decodeClosedPositions({ ...page, portfolio_closed: null, portfolio_closed_totals: {}, cash_balances: null })).toThrow('Invalid closed positions response')
  })
  it('preserves transaction body and validates currencies and records', async () => {
    const controller = new AbortController()
    const payload = { transactions: [{ id: 'regular_8', transaction_type: 'regular', date: '03-Jan-25', type: 'Cash in', cash_flow: '12.50' }], currencies: ['USD'], total_items: 1, current_page: 1, total_pages: 1 }
    http.post.mockResolvedValue({ data: payload })
    expect(await getTransactions(null, '2025-12-31', 1, 25, '', {}, { signal: controller.signal })).toEqual(payload)
    expect(http.post).toHaveBeenCalledWith('/transactions/api/get_transactions_table/',
      { page: 1, itemsPerPage: 25, search: '', dateFrom: null, dateTo: '2025-12-31', sortBy: {} },
      { signal: controller.signal })
    expect(() => decodeTransactions({ ...payload, currencies: null })).toThrow('Invalid transactions response')
    expect(() => decodeTransactions({ ...payload, transactions: [{ id: 8 }] })).toThrow('Invalid transactions response')
  })
  it('preserves raw FX strings and checks database table containers', async () => {
    const page = { total_items: 1, current_page: 1, total_pages: 1 }
    const fx = { results: [{ id: 1, date: '2025-01-01', from_currency: 'USD', to_currency: 'EUR', rate: '0.912345678' }], count: 1, current_page: 1, total_pages: 1 }
    http.post.mockResolvedValue({ data: fx })
    expect((await getFXData({ startDate: '', endDate: '', page: 1, itemsPerPage: 25, sortBy: {}, search: '' })).results[0].rate).toBe('0.912345678')
    expect(http.post).toHaveBeenCalledWith('/database/api/fx/list_fx/', { startDate: '', endDate: '', page: 1, itemsPerPage: 25, sortBy: {}, search: '' })
    expect(() => decodeFxTable({ ...fx, count: '1' })).toThrow('Invalid FX table response')
    expect(decodeAccountsTable({ ...page, accounts: [{ id: 1, nav: '1,000.00' }], totals: { nav: '1,000.00' } }).totals).toEqual({ nav: '1,000.00' })
    expect(decodeBrokersTable({ ...page, items: [{ id: 1 }], totals: {} }).items).toHaveLength(1)
    expect(decodePricesTable({ ...page, prices: [{ id: 1, price: '10.00' }] }).prices).toHaveLength(1)
    expect(decodeSecuritiesTable({ ...page, securities: [{ id: 1, name: 'Bond' }] }).securities).toHaveLength(1)
    expect(() => decodeAccountsTable({ ...page, totals: {}, accounts: 'missing' })).toThrow('Invalid accounts table response')
  })
  it('keeps year values numeric', async () => {
    http.get.mockResolvedValue({ data: { table_years: [2024, 2025] } })
    expect(await getYearOptions()).toEqual([2024, 2025])
    http.get.mockResolvedValue({ data: { table_years: [{ text: '2025', value: 2025 }] } })
    await expect(getYearOptions()).rejects.toThrow('Invalid year options response')
  })
  it('accepts the confirmed all-account selection with a null ID', async () => {
    const backend = createPortfolioContextBackend(async () => undefined)
    http.post.mockResolvedValue({ data: { success: true, selected: { type: 'all', id: null } } })
    http.get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('user_settings')
      ? { selected_account_type: 'all', selected_account_id: null }
      : { settings: { table_date: '2025-12-31', default_currency: 'USD', digits: 2 } } }))
    await backend.updateAccount({ type: 'all', id: null })
    expect(http.post).toHaveBeenCalledWith('/users/api/update_user_data_for_new_account/', { type: 'all', id: null })
    expect(http.get).toHaveBeenCalledTimes(2)
  })
  it('propagates an effective-date refresh failure', async () => {
    const backend = createPortfolioContextBackend(async () => { throw new Error('refresh failed') })
    http.post.mockResolvedValue({ data: { requires_token_refresh: true, new_effective_date: '2025-12-31' } })
    await expect(backend.updateSettings({ effectiveCurrentDate: '2025-12-31', currency: 'USD', digits: 2 })).rejects.toThrow('refresh failed')
    expect(http.get).not.toHaveBeenCalled()
  })

})
