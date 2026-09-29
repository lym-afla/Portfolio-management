import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
const { auth } = vi.hoisted(() => ({
  auth: {
    sessionEpoch: 1,
    setTokens: vi.fn(),
    clearTokens: vi.fn(),
    setUser: vi.fn(),
  },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
let client: (typeof import('@/config/axiosConfig'))['default']
let coordinator: typeof import('@/config/axiosConfig')
let contextModule: typeof import('@/services/api/context')
let requests: InternalAxiosRequestConfig[]
function reply(
  config: InternalAxiosRequestConfig,
  data: unknown
): AxiosResponse {
  return { config, data, status: 200, statusText: 'OK', headers: {} }
}
function login(epoch: number) {
  auth.sessionEpoch = epoch
  localStorage.setItem('accessToken', `user-${epoch}-access`)
  localStorage.setItem('refreshToken', `user-${epoch}-refresh`)
}
beforeEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  localStorage.clear()
  login(1)
  requests = []
  coordinator = await import('@/config/axiosConfig')
  client = coordinator.default
  contextModule = await import('@/services/api/context')
  const transport = await import('@/services/http/client')
  transport.configureApiTransport(client)
})
afterEach(async () => {
  ;(await import('@/services/http/client')).configureApiTransport(null)
})
it.each([true, false])(
  'a late settings response from session A cannot refresh or read session B (refresh=%s)',
  async (refresh) => {
    const held = deferred<AxiosResponse>()
    let post!: InternalAxiosRequestConfig
    client.defaults.adapter = async (config) => {
      requests.push(config)
      if (config.url?.includes('update_dashboard_settings')) {
        post = config
        return held.promise
      }
      if (config.url?.includes('refresh-token'))
        return reply(config, {
          access: 'wrong-dated-access',
          refresh: 'wrong-dated-refresh',
        })
      if (config.url?.includes('user_settings'))
        return reply(config, {
          selected_account_type: 'all',
          selected_account_id: null,
        })
      return reply(config, {
        settings: {
          table_date: '2025-12-31',
          default_currency: 'EUR',
          digits: 4,
        },
      })
    }
    const backend = contextModule.createPortfolioContextBackend(
      coordinator.refreshTokenWithEffectiveDate,
      () => auth.sessionEpoch
    )
    const pending = backend.updateSettings({
      effectiveCurrentDate: '2025-12-31',
      currency: 'EUR',
      digits: 4,
    })
    const result = pending.then(
      () => null,
      (error) => error
    )
    await vi.waitFor(() => expect(post).toBeDefined())
    login(3) // Logout ends epoch 1; login begins epoch 3.
    held.resolve(
      reply(post, {
        table_date: '2025-12-31',
        default_currency: 'EUR',
        digits: 4,
        requires_token_refresh: refresh,
        ...(refresh ? { new_effective_date: '2025-12-31' } : {}),
      })
    )
    expect(await result).toMatchObject({
      message: expect.stringContaining('session ended'),
    })
    expect(requests.map((request) => request.url)).toEqual([
      '/users/api/update_dashboard_settings/',
    ])
    expect(localStorage.getItem('refreshToken')).toBe('user-3-refresh')
    expect(localStorage.getItem('accessToken')).toBe('user-3-access')
  }
)
it.each([null, '2026-08-31'])(
  'starts an independent new-session refresh while the old refresh is unresolved (date=%s)',
  async (date) => {
    const first = deferred<AxiosResponse>()
    const second = deferred<AxiosResponse>()
    client.defaults.adapter = (config) => {
      requests.push(config)
      return requests.length === 1 ? first.promise : second.promise
    }
    const old = coordinator.refreshSessionToken()
    const oldResult = old.then(
      () => null,
      (error) => error
    )
    await vi.waitFor(() => expect(requests).toHaveLength(1))
    login(3)
    const current = coordinator.refreshSessionToken(date)
    const currentResult = current.then(
      (value) => value,
      (error) => error
    )
    await vi.waitFor(() => expect(requests).toHaveLength(2))
    expect(JSON.parse(requests[1].data)).toEqual({
      refresh: 'user-3-refresh',
      ...(date ? { effective_current_date: date } : {}),
    })
    first.resolve(
      reply(requests[0], { access: 'old-access', refresh: 'old-refresh' })
    )
    expect(await oldResult).toMatchObject({
      message: expect.stringContaining('session ended'),
    })
    // Old-epoch cleanup must not detach B's pending queue: another B caller joins it.
    const joined = coordinator.refreshSessionToken()
    await Promise.resolve()
    expect(requests).toHaveLength(2)
    second.resolve(
      reply(requests[1], { access: 'new-access', refresh: 'new-refresh' })
    )
    expect(await currentResult).toBe('new-access')
    expect(await joined).toBe('new-access')
    expect(localStorage.getItem('refreshToken')).toBe('new-refresh')
  }
)
it('rejects an explicitly stale originating epoch before any refresh request', async () => {
  client.defaults.adapter = async (config) => {
    requests.push(config)
    return reply(config, { access: 'wrong', refresh: 'wrong' })
  }
  login(3)
  await expect(
    coordinator.refreshTokenWithEffectiveDate('2025-12-31', 1)
  ).rejects.toThrow('session ended')
  expect(requests).toHaveLength(0)
  expect(localStorage.getItem('refreshToken')).toBe('user-3-refresh')
})
it('does not read back session B after session A logs out during its required refresh', async () => {
  const held = deferred<AxiosResponse>()
  let refreshPost!: InternalAxiosRequestConfig
  client.defaults.adapter = async (config) => {
    requests.push(config)
    if (config.url?.includes('update_dashboard_settings'))
      return reply(config, {
        table_date: '2025-12-31',
        default_currency: 'EUR',
        digits: 4,
        requires_token_refresh: true,
        new_effective_date: '2025-12-31',
      })
    if (config.url?.includes('refresh-token')) {
      refreshPost = config
      return held.promise
    }
    throw new Error('Unexpected readback after session change')
  }
  const backend = contextModule.createPortfolioContextBackend(
    coordinator.refreshTokenWithEffectiveDate,
    () => auth.sessionEpoch
  )
  const pending = backend.updateSettings({
    effectiveCurrentDate: '2025-12-31',
    currency: 'EUR',
    digits: 4,
  })
  const result = pending.then(
    () => null,
    (error) => error
  )
  await vi.waitFor(() => expect(refreshPost).toBeDefined())
  login(3)
  held.resolve(
    reply(refreshPost, {
      access: 'old-dated-access',
      refresh: 'old-dated-refresh',
    })
  )
  expect(await result).toMatchObject({
    message: expect.stringContaining('session ended'),
  })
  expect(requests).toHaveLength(2)
  expect(localStorage.getItem('refreshToken')).toBe('user-3-refresh')
})
it('does not dispatch an old settings mutation with new credentials when login changes before Axios dispatch', async () => {
  client.defaults.adapter = async (config) => {
    requests.push(config)
    return reply(config, {
      table_date: '2025-12-31',
      default_currency: 'EUR',
      digits: 4,
    })
  }
  const backend = contextModule.createPortfolioContextBackend(
    coordinator.refreshTokenWithEffectiveDate,
    () => auth.sessionEpoch
  )
  const pending = backend.updateSettings({
    effectiveCurrentDate: '2025-12-31',
    currency: 'EUR',
    digits: 4,
  })
  login(3)
  await expect(pending).rejects.toThrow('session ended')
  expect(requests).toHaveLength(0)
})
