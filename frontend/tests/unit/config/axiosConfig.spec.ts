import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

// Tests for the axios response interceptor's auth-failure handling.
//
// Reproduces the historical deadlock: when BOTH access AND refresh tokens are
// expired, the refresh-token request itself returns 401, re-enters the
// interceptor, hits the `if (isRefreshing)` branch, and waits on failedQueue
// forever — so the /login redirect is never reached.
//
// The fix: a 401 from the refresh-token endpoint itself is terminal; we
// force-logout (clear tokens + redirect) immediately rather than queueing.

// We must mock the auth store BEFORE importing axiosConfig (it calls
// useAuthStore at module-load).
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    clearTokens: vi.fn(),
    setUser: vi.fn(),
    setTokens: vi.fn(),
  }),
}))

// Mock logger to keep test output clean.
vi.mock('@/utils/logger', () => ({
  default: {
    log: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
  },
}))

// Capture the interceptor handlers by spying on axios.create / interceptors.
// We re-import axiosConfig per test so the module-level state (isRefreshing,
// failedQueue) is fresh.
let responseErrorHandler: (error: any) => Promise<any>

const mockPost = vi.fn()
const mockRequest = vi.fn()

beforeEach(async () => {
  vi.resetModules()
  // localStorage mock
  const store: Record<string, string> = {}
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: vi.fn((k: string) => store[k] ?? null),
      setItem: vi.fn((k: string, v: string) => { store[k] = String(v) }),
      removeItem: vi.fn((k: string) => { delete store[k] }),
      clear: vi.fn(() => { for (const k in store) delete store[k] }),
    },
    configurable: true,
    writable: true,
  })
  // Pre-populate tokens so the request interceptor has something to attach.
  store['accessToken'] = 'expired-access'
  store['refreshToken'] = 'expired-refresh'

  // window.location stub capturing href writes (the forceLogout redirect).
  const locationStub = {
    pathname: '/dashboard',
    href: '',
    assign: vi.fn(),
    replace: vi.fn(),
  }
  Object.defineProperty(globalThis, 'window', {
    value: { ...globalThis.window, location: locationStub },
    configurable: true,
    writable: true,
  })

  // Mock axios so we can capture interceptors and control post/request.
  vi.doMock('axios', () => {
    const interceptors = {
      request: { use: vi.fn() },
      response: {
        use: vi.fn((onFulfilled, onRejected) => {
          responseErrorHandler = onRejected
        }),
      },
    }
    const instance = {
      interceptors,
      post: mockPost,
      request: mockRequest,
      defaults: { headers: { common: {} } },
    }
    return {
      default: { create: vi.fn(() => instance) },
      create: vi.fn(() => instance),
    }
  })

  // Import after mocks are in place. This registers the response interceptor.
  await import('@/config/axiosConfig')
})

afterEach(() => {
  vi.doUnmock('axios')
  mockPost.mockReset()
  mockRequest.mockReset()
})

describe('axios response interceptor — auth failure handling', () => {
  it('forces logout (clears tokens, redirects) on refresh-token endpoint 401', async () => {
    // The refresh-token request itself returned 401 (refresh token expired).
    const refreshError = {
      config: { url: '/users/api/refresh-token/', method: 'post', headers: {} },
      response: { status: 401, data: {} },
    }

    const promise = responseErrorHandler(refreshError)
    await expect(promise).rejects.toBe(refreshError)

    // Tokens must be cleared.
    expect(localStorage.removeItem).toHaveBeenCalledWith('accessToken')
    expect(localStorage.removeItem).toHaveBeenCalledWith('refreshToken')
    expect(localStorage.removeItem).toHaveBeenCalledWith('effective_current_date')
    // Redirect to /login must have fired.
    expect(window.location.href).toBe('/login')
    // No refresh attempt, no queueing.
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('rejects cleanly when error.config is undefined (request-setup errors)', async () => {
    // Some axios errors (e.g. network/setup) have no `config` at all.
    const noConfigError = new Error('Network Error') as any
    // Deliberately no `config` property.

    const promise = responseErrorHandler(noConfigError)
    await expect(promise).rejects.toBe(noConfigError)
    // Should NOT crash trying to read `.url`.
    expect(window.location.href).toBe('')
  })

  it('rejects cleanly when error.config.url is missing', async () => {
    const noUrlError = {
      config: { headers: {} }, // no `url`
      response: { status: 500, data: {} },
    }

    const promise = responseErrorHandler(noUrlError)
    await expect(promise).rejects.toBe(noUrlError)
    expect(window.location.href).toBe('')
  })

  it('does not redirect to /login when already on /login (no redirect loop)', async () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/login', href: '' },
      configurable: true,
      writable: true,
    })
    const refreshError = {
      config: { url: '/users/api/refresh-token/', method: 'post', headers: {} },
      response: { status: 401, data: {} },
    }

    await expect(responseErrorHandler(refreshError)).rejects.toBe(refreshError)
    // Tokens still cleared, but href untouched (we're already on /login).
    expect(localStorage.removeItem).toHaveBeenCalledWith('accessToken')
    expect(window.location.href).toBe('')
  })
})
