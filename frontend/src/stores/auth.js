import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/services/api'
import router from '@/router'
import logger from '@/utils/logger'
// Imported for use inside fetchUserData() and initializeApp() (called at
// runtime, not at module load). Static import is safe because useAppStore()
// is only invoked inside functions; the app store's only runtime cross-store
// call (setAccountSelection -> useAuthStore) is likewise deferred to runtime.
import { useAppStore } from '@/stores/app'

/**
 * Auth Pinia store (Composition API style).
 *
 * Owns auth tokens, the current user object, and the app initialization
 * lifecycle. Persists accessToken / refreshToken to localStorage.
 */
export const useAuthStore = defineStore('auth', () => {
  // ---- State ----
  const accessToken = ref(localStorage.getItem('accessToken') || null)
  const refreshToken = ref(localStorage.getItem('refreshToken') || null)
  const user = ref(null)
  const isInitialized = ref(false)
  const isInitializing = ref(false)

  // ---- Getters ----
  const isAuthenticated = computed(
    () => !!accessToken.value && !!user.value
  )
  const currentUser = computed(() => user.value)

  // ---- Mutations / setters ----
  function setTokens({ accessToken: access, refreshToken: refresh }) {
    accessToken.value = access
    refreshToken.value = refresh
    if (access) localStorage.setItem('accessToken', access)
    else localStorage.removeItem('accessToken')
    if (refresh) localStorage.setItem('refreshToken', refresh)
    else localStorage.removeItem('refreshToken')
  }

  function setAccessToken(token) {
    accessToken.value = token
    if (token) localStorage.setItem('accessToken', token)
    else localStorage.removeItem('accessToken')
  }

  function setRefreshToken(token) {
    refreshToken.value = token
    if (token) localStorage.setItem('refreshToken', token)
    else localStorage.removeItem('refreshToken')
  }

  function setUser(newUser) {
    user.value = newUser
  }

  function clearTokens() {
    accessToken.value = null
    refreshToken.value = null
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
  }

  function setInitialized(value) {
    isInitialized.value = value
  }

  // ---- Actions ----
  async function fetchUserData() {
    try {
      const userData = await api.getUserProfile()
      setUser(userData)

      // Set account selection from user preferences or localStorage.
      // NOTE: account selection lives in the app store; mirror it there so
      // the UI stays consistent after login.
      const appStore = useAppStore()
      const savedSelection = JSON.parse(localStorage.getItem('accountSelection'))
      const selection = {
        type: userData.selected_account_type || savedSelection?.type || 'all',
        id: userData.selected_account_id || savedSelection?.id || null,
      }
      appStore.setAccountSelection(selection)

      return userData
    } catch (error) {
      logger.error('AuthStore', 'Failed to fetch user data:', error)
      throw error
    }
  }

  async function login(credentials) {
    try {
      const response = await api.login(
        credentials.username,
        credentials.password
      )
      setTokens({
        accessToken: response.access,
        refreshToken: response.refresh,
      })
      await fetchUserData()
      return { success: true }
    } catch (error) {
      logger.error('AuthStore', 'Login failed from store', error)
      throw error
    }
  }

  async function doRefreshToken() {
    logger.log('AuthStore', 'Refreshing token...')
    try {
      const response = await api.refreshToken(refreshToken.value)
      setTokens({
        accessToken: response.access,
        refreshToken: response.refresh || refreshToken.value,
      })
      await fetchUserData()
      return { success: true }
    } catch (error) {
      logger.error('AuthStore', 'Token refresh failed', error)
      clearTokens()
      setUser(null)
      return { success: false, error: error }
    }
  }

  async function logout() {
    logger.log('AuthStore', 'Logout action triggered')
    try {
      await api.logout()
    } catch (error) {
      logger.error('AuthStore', 'Error during logout:', error)
    } finally {
      clearTokens()
      setUser(null)
      router.push('/login')
    }
  }

  async function initializeApp() {
    const requestId = Date.now()
    logger.log('AuthStore', `[${requestId}] Starting initializeApp`)

    if (isInitialized.value) {
      logger.log('AuthStore', `[${requestId}] App already initialized, skipping`)
      return { success: !!user.value }
    }

    if (isInitializing.value) {
      logger.log(
        'AuthStore',
        `[${requestId}] App already initializing, waiting...`
      )
      const maxWaitTime = 2000
      const startTime = Date.now()

      while (isInitializing.value && Date.now() - startTime < maxWaitTime) {
        await new Promise((r) => setTimeout(r, 100))
      }

      if (isInitialized.value) {
        return { success: !!user.value }
      } else {
        logger.warn(
          'AuthStore',
          `[${requestId}] Waited too long for initialization, forcing completion`
        )
        setInitialized(true)
        isInitializing.value = false
        return { success: false }
      }
    }

    try {
      isInitializing.value = true
      logger.log('AuthStore', `[${requestId}] Set isInitializing=true`)

      const token = localStorage.getItem('accessToken')
      if (!token) {
        logger.log(
          'AuthStore',
          `[${requestId}] No token found, skipping initialization`
        )
        return { success: false }
      }

      logger.log(
        'AuthStore',
        `[${requestId}] Token found, setting tokens and fetching user data`
      )
      setTokens({
        accessToken: token,
        refreshToken: localStorage.getItem('refreshToken'),
      })

      try {
        await fetchUserData()
        logger.log('AuthStore', `[${requestId}] User data fetched successfully`)

        // Also fetch effective current date during initialization (lives in app store).
        const appStore = useAppStore()
        await appStore.fetchEffectiveCurrentDate()
        logger.log(
          'AuthStore',
          `[${requestId}] Effective current date fetched successfully`
        )

        return { success: true }
      } catch (error) {
        logger.error(
          'AuthStore',
          `[${requestId}] Error fetching user data:`,
          error
        )
        clearTokens()
        setUser(null)
        return { success: false }
      }
    } catch (error) {
      logger.error('AuthStore', `[${requestId}] Initialization error:`, error)
      return { success: false, error }
    } finally {
      logger.log(
        'AuthStore',
        `[${requestId}] Initialization completed, setting isInitialized=true`
      )
      setInitialized(true)
      isInitializing.value = false
    }
  }

  return {
    // state
    accessToken,
    refreshToken,
    user,
    isInitialized,
    isInitializing,
    // getters
    isAuthenticated,
    currentUser,
    // setters
    setTokens,
    setAccessToken,
    setRefreshToken,
    setUser,
    clearTokens,
    setInitialized,
    // actions
    login,
    doRefreshToken,
    logout,
    fetchUserData,
    initializeApp,
  }
})
