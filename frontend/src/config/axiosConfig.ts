import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'

const axiosInstance = axios.create({ baseURL: import.meta.env.VITE_API_URL })
const REFRESH_TOKEN_URL = '/users/api/refresh-token/'
let refreshQueue: Promise<string> | null = null

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
async function rotateToken(date: string | null): Promise<string> {
  const refresh = localStorage.getItem('refreshToken')
  if (!refresh) throw new Error('No refresh token available')
  const auth = useAuthStore()
  const generation = auth.sessionEpoch
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
/** One rotation queue for expired tokens and explicit effective-date changes. */
export function refreshSessionToken(
  date: string | null = null
): Promise<string> {
  if (!refreshQueue || date !== null) {
    const previous = refreshQueue
    const generation = useAuthStore().sessionEpoch
    const rotate = () => {
      if (useAuthStore().sessionEpoch !== generation)
        throw new Error('Authentication session ended')
      return rotateToken(date)
    }
    const operation = previous ? previous.then(rotate) : rotate()
    refreshQueue = operation
    // Rejections do not poison future retries, and cleanup has no unhandled rejection.
    const clear = () => {
      if (refreshQueue === operation) refreshQueue = null
    }
    operation.then(clear, clear)
  }
  return waitForRefreshQueue(refreshQueue)
}
async function waitForRefreshQueue(
  operation: Promise<string>
): Promise<string> {
  let current = operation
  let token = await current
  // A date update queued during the 401 refresh must finish before replaying reads.
  while (refreshQueue && refreshQueue !== current) {
    current = refreshQueue
    token = await current
  }
  return token
}
axiosInstance.interceptors.request.use((config) => {
  const sessionConfig = config as typeof config & { _authEpoch?: number }
  sessionConfig._authEpoch ??= useAuthStore().sessionEpoch
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
export const refreshTokenWithEffectiveDate = (date: string): Promise<string> =>
  refreshSessionToken(date)
export default axiosInstance
