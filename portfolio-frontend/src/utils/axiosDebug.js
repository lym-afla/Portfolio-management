/**
 * Debug utility to check axios configuration
 */
import axiosInstance from '@/config/axiosConfig'

export const debugAxiosConfiguration = () => {
  console.log('=== Axios Configuration Debug ===')

  // Check current tokens
  const accessToken = localStorage.getItem('accessToken')
  const refreshToken = localStorage.getItem('refreshToken')

  console.log('Available tokens:')
  console.log('- Access token exists:', !!accessToken)
  console.log(
    '- Access token preview:',
    accessToken ? `${accessToken.substring(0, 20)}...` : 'null'
  )
  console.log('- Refresh token exists:', !!refreshToken)

  // Test axios interceptor
  console.log('\n=== Testing Axios Request Interceptor ===')

  // Create a test request to see what headers are added
  const testConfig = {
    method: 'POST',
    url: '/users/api/update_dashboard_settings/',
    data: { test: 'debug' },
  }

  console.log('Original config:', {
    method: testConfig.method,
    url: testConfig.url,
    headers: testConfig.headers || {},
  })

  // Manually call the interceptor to see what happens
  const requestInterceptor = axiosInstance.interceptors.request.handlers[0]
  if (requestInterceptor) {
    const modifiedConfig = requestInterceptor.fulfilled(testConfig)
    console.log('Modified config after interceptor:', {
      method: modifiedConfig.method,
      url: modifiedConfig.url,
      headers: modifiedConfig.headers || {},
    })

    const hasAuthHeader =
      modifiedConfig.headers?.Authorization ||
      modifiedConfig.headers?.authorization
    console.log('Has Authorization header:', !!hasAuthHeader)
    console.log('Authorization header:', hasAuthHeader || 'MISSING')
  } else {
    console.error('❌ No request interceptor found!')
  }

  // Test actual axios call
  console.log('\n=== Testing Actual Axios Call ===')

  axiosInstance
    .get('/users/api/dashboard_settings/')
    .then((response) => {
      console.log('✅ Axios request successful:', response.status)
      console.log('Response data:', response.data)
    })
    .catch((error) => {
      console.log('❌ Axios request failed:', error.response?.status)
      console.log('Error data:', error.response?.data)

      // Check the request that was sent
      if (error.config) {
        console.log('Request URL:', error.config.url)
        console.log('Request headers:', error.config.headers)
        console.log(
          'Had Authorization header:',
          !!(
            error.config.headers?.Authorization ||
            error.config.headers?.authorization
          )
        )
      }
    })
}

export default debugAxiosConfiguration
