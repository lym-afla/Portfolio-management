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

const refreshToken = async () => {
  logger.log('Unknown', 'Attempting to refresh token...')
  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) {
    throw new Error('No refresh token available')
  }

  try {
    const response = await axios.post(
      `${process.env.VUE_APP_API_URL}/users/api/refresh-token/`,
      { refresh: refreshToken }
    )
    const { access, refresh } = response.data
    localStorage.setItem('accessToken', access)
    localStorage.setItem('refreshToken', refresh)
    logger.log('Unknown', 'Token refreshed successfully')
    return access
  } catch (error) {
    logger.error('Unknown', 'Error in refreshToken:', error)
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    throw error
  }
}

axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken')
    if (token) {
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

export default axiosInstance
