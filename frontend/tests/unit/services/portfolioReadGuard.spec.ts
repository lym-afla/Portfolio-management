import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AxiosInstance } from 'axios'
import {
  apiGet,
  apiPost,
  configureApiTransport,
  configurePortfolioReadGuard,
} from '@/services/http/client'
import { configurePortfolioContextBackend } from '@/services/api/context'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
afterEach(() => {
  configureApiTransport(null)
  configurePortfolioReadGuard(null)
  configurePortfolioContextBackend(null)
})
it('rejects financial reads during bootstrap, transition, failed recovery and logout, then resumes after reconciliation', async () => {
  localStorage.clear()
  setActivePinia(createPinia())
  const values = {
    accountSelection: { type: 'all' as const, id: null },
    effectiveCurrentDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  }
  const get = vi.fn(async (url: string) => ({
    data: url.includes('get_account_choices')
      ? { options: [['All', values.accountSelection]] }
      : url.includes('dashboard_settings')
        ? { choices: { default_currency: [['USD', 'Dollar']] } }
        : 'ok',
  }))
  const post = vi.fn()
  configureApiTransport({ get, post } as unknown as AxiosInstance)
  const read = vi.fn(async () => values)
  let release!: () => void
  configurePortfolioContextBackend({
    read,
    updateAccount: vi.fn(),
    updateSettings: async () => {
      await new Promise<void>((resolve) => {
        release = resolve
      })
      throw new Error('Connection lost')
    },
  })
  const store = usePortfolioContextStore()
  configurePortfolioReadGuard(() => store.canRead)
  await expect(apiGet('/dashboard/api/get-summary/')).rejects.toThrow(
    'Portfolio context is not ready'
  )
  await store.reconcileContext()
  expect(await apiGet('/dashboard/api/get-summary/')).toBe('ok')
  const pending = store.changeContext({ digits: 3 })
  const rejected = expect(pending).rejects.toThrow('Connection lost')
  await expect(
    apiPost('/open_positions/api/get_open_positions_table/', {})
  ).rejects.toThrow('Portfolio context is not ready')
  expect(post).not.toHaveBeenCalled()
  read.mockRejectedValue(new Error('Offline'))
  release()
  await rejected
  expect(store.isReady).toBe(false)
  await expect(apiGet('/dashboard/api/get-summary/')).rejects.toThrow(
    'Portfolio context is not ready'
  )
  read.mockResolvedValue(values)
  await store.reconcileContext()
  expect(await apiGet('/dashboard/api/get-summary/')).toBe('ok')
  store.resetContext()
  await expect(apiGet('/dashboard/api/get-summary/')).rejects.toThrow(
    'Portfolio context is not ready'
  )
})
