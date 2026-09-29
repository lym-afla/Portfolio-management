import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiTransport } from '@/services/http/client'

const http = { get: vi.fn(), post: vi.fn() }
vi.mock('@/config/axiosConfig', () => ({ default: http }))
vi.mock('@/stores/app', () => ({ useAppStore: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: vi.fn() }))
vi.mock('@/utils/logger', () => ({ default: { log: vi.fn(), error: vi.fn(), warn: vi.fn() } }))

beforeEach(() => {
  configureApiTransport(http)
  http.get.mockReset()
  http.post.mockReset()
})
afterEach(() => configureApiTransport(null))

describe('legacy API facade', () => {
  it('retains existing exports and forwards cancellation', async () => {
    const api = await import('@/services/api')
    expect(typeof api.getOpenPositions).toBe('function')
    expect(typeof api.getTransactions).toBe('function')
    expect(typeof api.getFXData).toBe('function')
    http.post.mockResolvedValue({ data: {
      portfolio_open: [], portfolio_open_totals: {}, cash_balances: {},
      total_items: 0, current_page: 1, total_pages: 1,
    } })
    const controller = new AbortController()
    await api.getOpenPositions(null, '2025-12-31', 1, 25, '', {}, { signal: controller.signal })
    expect(http.post).toHaveBeenCalledWith('/open_positions/api/get_open_positions_table/',
      { dateFrom: null, dateTo: '2025-12-31', page: 1, itemsPerPage: 25, search: '', sortBy: {} },
      expect.objectContaining({ signal: controller.signal }))
  })
})
it('captures logout authorization before the auth store invalidates local credentials', async () => {
  const api = await import('@/services/api')
  localStorage.setItem('accessToken', 'synthetic-access')
  localStorage.setItem('refreshToken', 'synthetic-refresh')
  http.post.mockResolvedValue({ data: { success: true } })
  const pending = api.logout(); localStorage.clear(); await pending
  expect(http.post).toHaveBeenCalledWith('/users/api/logout/', { refresh_token: 'synthetic-refresh' }, { headers: { Authorization: 'Bearer synthetic-access' } })
})
