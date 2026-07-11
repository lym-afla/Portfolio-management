/**
 * Authentication Debugging Utility
 * Helps diagnose frontend authentication and session issues
 */
import store from '@/store'
import logger from '@/utils/logger'

class AuthDebugger {
  constructor() {
    this.debugMode = true
  }

  log(message, data = null) {
    if (this.debugMode) {
      console.log(`[AuthDebugger] ${message}`, data || '')
      logger.log('AuthDebugger', message, data)
    }
  }

  error(message, data = null) {
    console.error(`[AuthDebugger ERROR] ${message}`, data || '')
    logger.error('AuthDebugger', message, data)
  }

  /**
   * Phase 1: Check token storage in localStorage
   */
  checkTokenStorage() {
    this.log('=== Phase 1: Token Storage Check ===')

    const accessToken = localStorage.getItem('accessToken')
    const refreshToken = localStorage.getItem('refreshToken')

    const tokenStatus = {
      accessToken: {
        exists: !!accessToken,
        length: accessToken ? accessToken.length : 0,
        preview: accessToken ? `${accessToken.substring(0, 20)}...` : 'null',
        startsWithBearer: accessToken ? accessToken.startsWith('eyJ') : false,
      },
      refreshToken: {
        exists: !!refreshToken,
        length: refreshToken ? refreshToken.length : 0,
        preview: refreshToken ? `${refreshToken.substring(0, 20)}...` : 'null',
        startsWithBearer: refreshToken ? refreshToken.startsWith('eyJ') : false,
        isUndefined: refreshToken === 'undefined',
        isCorrupted:
          refreshToken &&
          refreshToken.length < 50 &&
          !refreshToken.startsWith('eyJ'),
      },
    }

    this.log('Token storage status:', tokenStatus)

    // Check if tokens are valid JWT format
    if (accessToken && !accessToken.startsWith('eyJ')) {
      this.error('Access token is not in valid JWT format')
    }
    if (refreshToken === 'undefined') {
      this.error(
        'Refresh token is literally "undefined" - corrupted token detected'
      )
    }
    if (
      refreshToken &&
      refreshToken.length < 50 &&
      !refreshToken.startsWith('eyJ')
    ) {
      this.error('Refresh token appears to be corrupted or invalid')
    }

    return tokenStatus
  }

  /**
   * Phase 1: Verify authentication status in Vuex store
   */
  checkStoreAuthentication() {
    this.log('=== Phase 1: Store Authentication Check ===')

    const storeState = store.state
    const isAuthenticated = store.getters.isAuthenticated

    const authStatus = {
      isAuthenticated,
      hasAccessToken: !!storeState.accessToken,
      hasRefreshToken: !!storeState.refreshToken,
      hasUser: !!storeState.user,
      user: storeState.user
        ? {
            id: storeState.user.id,
            username: storeState.user.username,
            email: storeState.user.email,
          }
        : null,
      isInitialized: storeState.isInitialized,
      isInitializing: storeState.isInitializing,
    }

    this.log('Store authentication status:', authStatus)

    // Check for inconsistencies
    if (isAuthenticated && !storeState.user) {
      this.error('Authenticated but no user data in store')
    }
    if (isAuthenticated && !storeState.accessToken) {
      this.error('Authenticated but no access token in store')
    }

    return authStatus
  }

  /**
   * Phase 2: Decode JWT tokens to check expiration
   */
  decodeJWT(token) {
    try {
      const base64Url = token.split('.')[1]
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map(function (c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
          })
          .join('')
      )
      return JSON.parse(jsonPayload)
    } catch (error) {
      this.error('Failed to decode JWT token:', error.message)
      return null
    }
  }

  checkTokenExpiration() {
    this.log('=== Token Expiration Check ===')

    const accessToken = localStorage.getItem('accessToken')
    const refreshToken = localStorage.getItem('refreshToken')

    const tokenInfo = {}

    if (accessToken) {
      const accessDecoded = this.decodeJWT(accessToken)
      if (accessDecoded) {
        tokenInfo.accessToken = {
          exp: accessDecoded.exp,
          expDate: new Date(accessDecoded.exp * 1000).toISOString(),
          isExpired: Date.now() >= accessDecoded.exp * 1000,
          timeUntilExpiry: accessDecoded.exp * 1000 - Date.now(),
        }
      }
    }

    if (refreshToken) {
      const refreshDecoded = this.decodeJWT(refreshToken)
      if (refreshDecoded) {
        tokenInfo.refreshToken = {
          exp: refreshDecoded.exp,
          expDate: new Date(refreshDecoded.exp * 1000).toISOString(),
          isExpired: Date.now() >= refreshDecoded.exp * 1000,
          timeUntilExpiry: refreshDecoded.exp * 1000 - Date.now(),
        }
      }
    }

    this.log('Token expiration info:', tokenInfo)

    if (tokenInfo.accessToken?.isExpired) {
      this.error('Access token is expired')
    }
    if (tokenInfo.refreshToken?.isExpired) {
      this.error('Refresh token is expired')
    }

    return tokenInfo
  }

  /**
   * Comprehensive authentication check
   */
  runFullDiagnostic() {
    this.log('🔍 Starting Full Authentication Diagnostic')

    const results = {
      timestamp: new Date().toISOString(),
      tokenStorage: this.checkTokenStorage(),
      storeAuth: this.checkStoreAuthentication(),
      tokenExpiration: this.checkTokenExpiration(),
    }

    // Overall assessment
    const issues = []

    if (!results.tokenStorage.accessToken.exists) {
      issues.push('No access token in localStorage')
    }
    if (!results.storeAuth.isAuthenticated) {
      issues.push('Not authenticated in Vuex store')
    }
    if (results.tokenExpiration.accessToken?.isExpired) {
      issues.push('Access token is expired')
    }
    if (!results.storeAuth.hasUser) {
      issues.push('No user data in store')
    }
    if (results.tokenStorage.refreshToken.isUndefined) {
      issues.push('Refresh token is corrupted (literally "undefined")')
    }
    if (results.tokenStorage.refreshToken.isCorrupted) {
      issues.push('Refresh token appears to be corrupted or invalid')
    }

    // Determine specific recommendation
    let recommendation = 'Authentication looks healthy'
    if (issues.length > 0) {
      if (
        issues.some(
          (issue) => issue.includes('corrupted') || issue.includes('undefined')
        )
      ) {
        recommendation =
          'Run authDebug.fixCorruptedTokens() to fix corrupted tokens, then re-login'
      } else {
        recommendation = 'Fix authentication issues before proceeding'
      }
    }

    results.assessment = {
      isHealthy: issues.length === 0,
      issues,
      recommendation,
    }

    this.log('📊 Diagnostic Results:', results)

    if (!results.assessment.isHealthy) {
      this.error('Authentication issues detected:', issues)
    } else {
      this.log('✅ Authentication diagnostic passed')
    }

    return results
  }

  /**
   * Fix corrupted refresh token issue
   */
  fixCorruptedTokens() {
    this.log('=== Fixing Corrupted Tokens ===')

    const refreshToken = localStorage.getItem('refreshToken')
    const issues = []

    if (
      refreshToken === 'undefined' ||
      refreshToken === 'null' ||
      (refreshToken &&
        refreshToken.length < 50 &&
        !refreshToken.startsWith('eyJ'))
    ) {
      this.error('Corrupted refresh token detected, attempting to fix...')
      issues.push('Corrupted refresh token')

      // Remove corrupted refresh token
      localStorage.removeItem('refreshToken')
      if (window.store) {
        window.store.commit('CLEAR_TOKENS')
      }

      this.log('Removed corrupted refresh token from localStorage and store')
      console.log('[AuthDebugger] 🛠️ Removed corrupted refresh token')
    }

    const accessToken = localStorage.getItem('accessToken')
    if (accessToken && !accessToken.startsWith('eyJ')) {
      this.error('Corrupted access token detected, attempting to fix...')
      issues.push('Corrupted access token')

      // Remove corrupted access token
      localStorage.removeItem('accessToken')
      if (window.store) {
        window.store.commit('CLEAR_TOKENS')
      }

      this.log('Removed corrupted access token from localStorage and store')
      console.log('[AuthDebugger] 🛠️ Removed corrupted access token')
    }

    if (issues.length > 0) {
      this.log(`Fixed ${issues.length} token issues: ${issues.join(', ')}`)
      console.log('[AuthDebugger] 🔄 Please log in again to get fresh tokens')
      console.log('[AuthDebugger] 🔄 Redirecting to login page...')

      // Redirect to login after a short delay
      setTimeout(() => {
        if (window.router) {
          window.router.push('/login')
        } else {
          window.location.href = '/login'
        }
      }, 2000)

      return { fixed: true, issues }
    }

    return { fixed: false, issues: [] }
  }

  /**
   * Monitor API requests for authentication headers
   */
  monitorApiRequests() {
    this.log('=== API Request Monitor Setup ===')

    // Store original fetch
    const originalFetch = window.fetch
    const originalXHROpen = XMLHttpRequest.prototype.open
    const originalXHRSend = XMLHttpRequest.prototype.send

    // Monitor fetch requests
    window.fetch = async function (...args) {
      const [url, options] = args
      const hasAuthHeader =
        options?.headers?.Authorization || options?.headers?.['authorization']

      if (url.includes('/api/') && !hasAuthHeader) {
        console.warn(`[AuthDebugger] API request without auth header: ${url}`)
      }

      return originalFetch.apply(this, args)
    }

    // Monitor XMLHttpRequest (used by axios)
    XMLHttpRequest.prototype.open = function (method, url, ...args) {
      this._url = url
      this._method = method
      return originalXHROpen.apply(this, [method, url, ...args])
    }

    XMLHttpRequest.prototype.send = function (...args) {
      if (this._url?.includes('/api/')) {
        const authHeader =
          this.getRequestHeader?.('Authorization') ||
          this.getRequestHeader?.('authorization')
        if (!authHeader) {
          console.warn(
            `[AuthDebugger] XHR API request without auth header: ${this._method} ${this._url}`
          )
        }
      }
      return originalXHRSend.apply(this, args)
    }

    this.log('API request monitoring enabled')
  }
}

export default new AuthDebugger()
