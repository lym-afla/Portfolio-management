import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/services/api'
import router from '@/router'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { refreshSessionToken } from '@/config/axiosConfig'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('accessToken') || null)
  const refreshToken = ref(localStorage.getItem('refreshToken') || null)
  const user = ref(null)
  const isInitialized = ref(false)
  const isInitializing = ref(false)
  const sessionEpoch = ref(0)
  let initialization: Promise<{ success: boolean }> | null = null
  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)
  const currentUser = computed(() => user.value)
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
  function setTokens({ accessToken: access, refreshToken: refresh }) {
    setAccessToken(access)
    setRefreshToken(refresh)
  }
  function setUser(value) {
    user.value = value
  }
  function setInitialized(value) {
    isInitialized.value = value
  }
  function clearTokens() {
    sessionEpoch.value++
    user.value = null
    setTokens({ accessToken: null, refreshToken: null })
    localStorage.removeItem('effective_current_date')
    usePortfolioContextStore().resetContext()
    initialization = null
    isInitializing.value = false
    isInitialized.value = false
  }
  async function fetchUserData() {
    const generation = sessionEpoch.value
    const profile = await api.getUserProfile()
    if (generation !== sessionEpoch.value)
      throw new Error('Authentication session ended')
    setUser(profile)
    return profile
  }
  async function synchronizeContext() {
    // A recoverable context outage keeps the authenticated recovery UI available.
    try {
      await usePortfolioContextStore().reconcileContext()
    } catch {
      /* Store owns recovery/error state. */
    }
  }
  async function login(credentials) {
    clearTokens()
    const generation = sessionEpoch.value
    const response = await api.login(credentials.username, credentials.password)
    if (generation !== sessionEpoch.value)
      throw new Error('Authentication session ended')
    setTokens({ accessToken: response.access, refreshToken: response.refresh })
    await fetchUserData()
    await synchronizeContext()
    return { success: true }
  }
  async function doRefreshToken() {
    try {
      await refreshSessionToken()
      await fetchUserData()
      return { success: true }
    } catch (error) {
      return { success: false, error }
    }
  }
  async function logout() {
    // Capture the logout request's credentials before invalidating local work.
    const request = api.logout()
    clearTokens()
    setUser(null)
    try {
      await request
    } catch {
      /* Local logout is authoritative even offline. */
    }
    await router.push('/login')
  }
  function initializeApp(): Promise<{ success: boolean }> {
    if (initialization) return initialization
    if (isInitialized.value) return Promise.resolve({ success: !!user.value })
    const generation = sessionEpoch.value
    isInitializing.value = true
    initialization = (async () => {
      try {
        if (!accessToken.value) return { success: false }
        await fetchUserData()
        await synchronizeContext()
        return { success: generation === sessionEpoch.value && !!user.value }
      } catch {
        if (generation === sessionEpoch.value) {
          clearTokens()
          setUser(null)
        }
        return { success: false }
      } finally {
        if (generation === sessionEpoch.value) {
          isInitialized.value = true
          isInitializing.value = false
        }
      }
    })()
    return initialization
  }
  return {
    accessToken,
    refreshToken,
    user,
    isInitialized,
    isInitializing,
    sessionEpoch,
    isAuthenticated,
    currentUser,
    setTokens,
    setAccessToken,
    setRefreshToken,
    setUser,
    clearTokens,
    setInitialized,
    login,
    doRefreshToken,
    logout,
    fetchUserData,
    initializeApp,
  }
})
