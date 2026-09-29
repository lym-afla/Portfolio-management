import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'

const axiosInstance = axios.create({ baseURL: import.meta.env.VITE_API_URL })
const REFRESH_TOKEN_URL = '/users/api/refresh-token/'
interface RefreshQueue {
  readonly epoch: number
  readonly operation: Promise<string>
}
let refreshQueue: RefreshQueue | null = null
export const getAuthSessionEpoch = (): number => useAuthStore().sessionEpoch
function assertSession(epoch: number): void {
  if (getAuthSessionEpoch() !== epoch)
    throw new Error('Authentication session ended')
}

function forceLogout(): void {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')
  localStorage.removeItem('effective_current_date')
  const auth = useAuthStore()
  auth.clearTokens()
  auth.setUser(null)
  if (typeof window !== 'undefined' && window.location.pathname !== '/login')
    window.location.href = '/login'
}
async function rotateToken(
  date: string | null,
  generation: number
): Promise<string> {
  assertSession(generation)
  const refresh = localStorage.getItem('refreshToken')
  if (!refresh) throw new Error('No refresh token available')
  const auth = useAuthStore()
  const data: { refresh: string; effective_current_date?: string } = { refresh }
  if (date) data.effective_current_date = date
  const config: AxiosRequestConfig & { _authEpoch: number } = {
    _authEpoch: generation,
  }
  const response = await axiosInstance.post(REFRESH_TOKEN_URL, data, config)
  if (
    auth.sessionEpoch !== generation ||
    localStorage.getItem('refreshToken') !== refresh
  )
    throw new Error('Authentication session ended')
  const tokens = response.data
  if (typeof tokens.access !== 'string' || typeof tokens.refresh !== 'string')
    throw new Error('Invalid token refresh response')
  auth.setTokens({ accessToken: tokens.access, refreshToken: tokens.refresh })
  // Also persist here for clients using this transport without a mounted auth view.
  localStorage.setItem('accessToken', tokens.access)
  localStorage.setItem('refreshToken', tokens.refresh)
  if (tokens.effective_current_date)
    localStorage.setItem(
      'effective_current_date',
      tokens.effective_current_date
    )
  return tokens.access
}
/** One rotation queue per auth epoch; a new session never waits for the old one. */
export function refreshSessionToken(
  date: string | null = null,
  originatingEpoch: number = getAuthSessionEpoch()
): Promise<string> {
  if (getAuthSessionEpoch() !== originatingEpoch)
    return Promise.reject(new Error('Authentication session ended'))
  const ownedQueue =
    refreshQueue?.epoch === originatingEpoch ? refreshQueue : null
  if (ownedQueue && date === null) return waitForRefreshQueue(ownedQueue)

  const rotate = () => rotateToken(date, originatingEpoch)
  const operation = ownedQueue ? ownedQueue.operation.then(rotate) : rotate()
  const next: RefreshQueue = { epoch: originatingEpoch, operation }
  refreshQueue = next
  // An old epoch's settlement cannot detach a newer session's in-flight queue.
  const clear = () => {
    if (refreshQueue === next) refreshQueue = null
  }
  operation.then(clear, clear)
  return waitForRefreshQueue(next)
}
async function waitForRefreshQueue(queue: RefreshQueue): Promise<string> {
  let current = queue
  let token = await current.operation
  assertSession(queue.epoch)
  // Same-session date updates must finish before retrying waiting financial reads.
  while (
    refreshQueue &&
    refreshQueue.epoch === queue.epoch &&
    refreshQueue !== current
  ) {
    current = refreshQueue
    token = await current.operation
    assertSession(queue.epoch)
  }
  return token
}
axiosInstance.interceptors.request.use((config) => {
  const sessionConfig = config as typeof config & { _authEpoch?: number }
  sessionConfig._authEpoch ??= getAuthSessionEpoch()
  assertSession(sessionConfig._authEpoch)
  const token = localStorage.getItem('accessToken')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (!original?.url) return Promise.reject(error)
    if (
      original._authEpoch !== undefined &&
      original._authEpoch !== useAuthStore().sessionEpoch
    )
      return Promise.reject(new Error('Authentication session ended'))
    if (
      error.response?.status === 401 &&
      original.url.includes(REFRESH_TOKEN_URL)
    ) {
      forceLogout()
      return Promise.reject(error)
    }
    if (
      original.url.includes('tinkoff-tokens') &&
      error.response?.data?.error_code
    )
      return Promise.reject(error)
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const token = await refreshSessionToken()
      original.headers.Authorization = `Bearer ${token}`
      return axiosInstance.request(original)
    }
    return Promise.reject(error)
  }
)
export const refreshTokenWithEffectiveDate = (
  date: string,
  originatingEpoch: number = getAuthSessionEpoch()
): Promise<string> => refreshSessionToken(date, originatingEpoch)
export default axiosInstance
