import axios from 'axios'
import store from '@/store'
import router from '@/router'
import { logout } from '@/services/api'

const axiosInstance = axios.create({
  baseURL: 'http://localhost:8000',
})

axiosInstance.interceptors.request.use(async config => {
  const token = store.state.accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  } else {
    console.log('No token found in the state')
  }
  return config
}, error => {
  return Promise.reject(error)
})

axiosInstance.interceptors.response.use(
  response => response,
  async error => {
    console.log('Error in axiosInstance.interceptors.response.use:', error)
    const originalRequest = error.config
    
    // Check if the error is due to an invalid or expired token
    if (error.response.status === 401 && error.response.data.code === "token_not_valid") {
      if (!originalRequest._retry && store.state.refreshToken) {
        console.log('Attempting to refresh token...')
        originalRequest._retry = true
        try {
          const refreshed = await store.dispatch('refreshToken')
          console.log('Token refresh attempt result:', refreshed)
          if (refreshed) {
            return axiosInstance(originalRequest)
          }
        } catch (refreshError) {
          console.error('Token refresh failed:', refreshError)
        }
      }
      
      // If we reach here, it means either:
      // 1. We've already tried to refresh and failed
      // 2. We don't have a refresh token
      // 3. The refresh attempt failed
      // In all these cases, we should log out the user
      console.log('Authentication failed. Logging out user.')
      try {
        await logout()
        store.commit('CLEAR_TOKENS')
        router.push('/login')
      } catch (logoutError) {
        console.error('Error during logout:', logoutError)
      }
      return Promise.reject(error)
    }
    
    return Promise.reject(error)
  }
)

export default axiosInstance