import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import * as api from '@/services/api'
vi.mock('@/services/api', () => ({
  getUserProfile: vi.fn(),
  logout: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/router', () => ({ default: { push: vi.fn() } }))
vi.mock('@/config/axiosConfig', () => ({ refreshSessionToken: vi.fn() }))
beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('accessToken', 'test-access')
  localStorage.setItem('refreshToken', 'test-refresh')
  setActivePinia(createPinia())
})
it('shares bootstrap reconciliation once and waits for its readiness', async () => {
  vi.mocked(api.getUserProfile).mockResolvedValue({ id: 1 })
  let finish!: () => void
  const context = usePortfolioContextStore()
  const reconcile = vi.spyOn(context, 'reconcileContext').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const auth = useAuthStore()
  const first = auth.initializeApp()
  const second = auth.initializeApp()
  await vi.waitFor(() => expect(reconcile).toHaveBeenCalledTimes(1))
  expect(auth.isInitialized).toBe(false)
  finish()
  await Promise.all([first, second])
  expect(auth.isAuthenticated).toBe(true)
})
it('logout invalidates an outstanding profile bootstrap immediately', async () => {
  let finish!: (value: unknown) => void
  vi.mocked(api.getUserProfile).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const auth = useAuthStore()
  const bootstrap = auth.initializeApp()
  await Promise.resolve()
  await auth.logout()
  finish({ id: 1 })
  await bootstrap
  expect(auth.user).toBeNull()
  expect(auth.isAuthenticated).toBe(false)
  expect(usePortfolioContextStore().isReady).toBe(false)
})
it('clears the user together with credentials when ending a session', () => {
  const auth = useAuthStore()
  auth.setUser({ id: 1 })
  auth.clearTokens()
  expect(auth.user).toBeNull()
})
