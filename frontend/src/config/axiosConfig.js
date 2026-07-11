import axios from 'axios'
import logger from '@/utils/logger'

const axiosInstance = axios.create({
  baseURL: process.env.VUE_APP_API_URL,
})

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

const refreshToken = async (newEffectiveDate = null) => {
  logger.log('Unknown', 'Attempting to refresh token...')
  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) {
    logger.error('AuthDebugger', 'No refresh token available for token refresh')
    console.error('[AuthDebugger] ❌ No refresh token available')
    throw new Error('No refresh token available')
  }

  try {
    logger.log('AuthDebugger', 'Sending refresh token request...')
    console.log('[AuthDebugger] 🔄 Refreshing token...')

    const requestData = { refresh: refreshToken }

    // Include effective_current_date if provided (for updating JWT payload)
    if (newEffectiveDate) {
      requestData.effective_current_date = newEffectiveDate
      logger.log(
        'AuthDebugger',
        `Updating effective_current_date to: ${newEffectiveDate}`
      )
      console.log(
        `[AuthDebugger] 📅 Updating effective_date to: ${newEffectiveDate}`
      )
    }

    const response = await axiosInstance.post(
      '/users/api/refresh-token/',
      requestData
    )

    const { access, refresh, effective_current_date } = response.data
    localStorage.setItem('accessToken', access)
    localStorage.setItem('refreshToken', refresh)

    // Store effective_current_date if present in response
    if (effective_current_date) {
      localStorage.setItem('effective_current_date', effective_current_date)
      logger.log(
        'AuthDebugger',
        `Stored effective_current_date: ${effective_current_date}`
      )
      console.log(
        `[AuthDebugger] 📅 Stored effective_date: ${effective_current_date}`
      )
    }

    logger.log('AuthDebugger', 'Token refreshed successfully')
    console.log('[AuthDebugger] ✅ Token refreshed successfully')

    // Update Vuex store with new tokens
    if (window.store) {
      window.store.commit('SET_TOKENS', {
        accessToken: access,
        refreshToken: refresh,
      })
    }

    return access
  } catch (error) {
    logger.error('AuthDebugger', 'Error in refreshToken:', error)
    console.error('[AuthDebugger] ❌ Token refresh failed:', error)

    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('effective_current_date') // Also clear effective date

    // Clear Vuex store
    if (window.store) {
      window.store.commit('CLEAR_TOKENS')
      window.store.commit('SET_USER', null)
    }

    throw error
  }
}

axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken')

    // Ensure headers object exists
    if (!config.headers) {
      config.headers = {}
    }

    // Enhanced debugging for authentication
    if (config.url?.includes('/api/')) {
      logger.log(
        'Axios',
        `Request: ${config.method?.toUpperCase()} ${config.url}`
      )
      logger.log('Axios', `Token exists: ${!!token}`)
      logger.log(
        'Axios',
        `Token preview: ${token ? `${token.substring(0, 20)}...` : 'null'}`
      )
      logger.log('Axios', `Headers before:`, config.headers)

      if (token) {
        config.headers['Authorization'] = `Bearer ${token}`
        logger.log('Axios', 'Authorization header added')
        logger.log('Axios', `Headers after:`, config.headers)
      } else {
        logger.error('Axios', 'No token available for API request')
        console.error(
          `[AuthDebugger] ❌ API request without token: ${config.method?.toUpperCase()} ${config.url}`
        )
      }
    } else if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }

    return config
  },
  (error) => Promise.reject(error)
)

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Handle Tinkoff API errors
    if (originalRequest.url.includes('tinkoff-tokens')) {
      logger.log('Unknown', 'Tinkoff API error detected:', error.response?.data)

      // Pass through the error from backend without attempting token refresh
      if (error.response?.data?.error_code) {
        return Promise.reject({
          response: {
            status: error.response.status,
            data: {
              error: error.response.data.error,
              error_code: error.response.data.error_code,
            },
          },
        })
      }
    }

    // Enhanced debugging for authentication failures
    if (error.response?.status === 401) {
      logger.error(
        'Axios',
        `401 Unauthorized for: ${originalRequest.method?.toUpperCase()} ${originalRequest.url}`
      )
      console.error(
        `[AuthDebugger] 🔒 401 Unauthorized: ${originalRequest.method?.toUpperCase()} ${originalRequest.url}`
      )

      // Check if we have tokens
      const hasAccessToken = !!localStorage.getItem('accessToken')
      const hasRefreshToken = !!localStorage.getItem('refreshToken')
      logger.log(
        'Axios',
        `Has access token: ${hasAccessToken}, Has refresh token: ${hasRefreshToken}`
      )
    }

    // Handle JWT token refresh for other 401 errors
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalRequest.headers['Authorization'] = `Bearer ${token}`
            return axiosInstance(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const newToken = await refreshToken()
        processQueue(null, newToken)
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`
        return axiosInstance(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        localStorage.removeItem('accessToken')
        localStorage.removeItem('refreshToken')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

// Function to refresh token with new effective date
export const refreshTokenWithEffectiveDate = async (newEffectiveDate) => {
  logger.log(
    'AuthDebugger',
    `Force refreshing token with new effective_date: ${newEffectiveDate}`
  )
  console.log(
    `[AuthDebugger] 🔄 Force refreshing token with effective_date: ${newEffectiveDate}`
  )

  try {
    const newToken = await refreshToken(newEffectiveDate)
    return newToken
  } catch (error) {
    logger.error(
      'AuthDebugger',
      'Failed to refresh token with new effective date:',
      error
    )
    throw error
  }
}

export default axiosInstance
