import axios from 'axios'
import store from '@/store'
// import router from '@/router'

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
    if (error.response.status === 401 && !originalRequest._retry && store.state.refreshToken) {
      console.log('Refreshing token...', !originalRequest._retry)
      originalRequest._retry = true
      try {
        const refreshed = await store.dispatch('refreshToken')
        console.log('Token refreshed:', refreshed)
        if (refreshed) {
          return axiosInstance(originalRequest)
        }
      } catch (refreshError) {
        console.error('Token refresh failed:', refreshError)
        store.commit('CLEAR_TOKENS')
      }
    }
    return Promise.reject(error)
  }
)

export default axiosInstance