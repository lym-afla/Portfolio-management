import { createStore } from 'vuex'
import * as api from '@/services/api'
import router from '@/router'
import logger from '@/utils/logger'
// import axios from 'axios'

export default createStore({
  state: {
    accessToken: localStorage.getItem('accessToken') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    user: null,
    pageTitle: '',
    loading: false,
    error: null,
    accountSelection: JSON.parse(localStorage.getItem('accountSelection')) || {
      type: 'all',
      id: null,
    },
    dataRefreshTrigger: 0,
    effectiveCurrentDate: null,
    selectedCurrency: null,
    tableSettings: {
      dateFrom: null,
      dateTo: null,
      timespan: 'all_time', // Set default timespan to 'all_time'
      page: 1,
      itemsPerPage: 25,
      search: '',
      sortBy: [],
    },
    itemsPerPageOptions: [10, 25, 50, 100],
    navChartParams: {
      frequency: 'Q',
      breakdown: 'none',
      dateRange: 'ytd',
      dateFrom: null,
      dateTo: null,
    },
    isInitialized: false,
    isInitializing: false,
  },
  mutations: {
    SET_TOKENS(state, { accessToken, refreshToken }) {
      state.accessToken = accessToken
      state.refreshToken = refreshToken
      localStorage.setItem('accessToken', accessToken)
      localStorage.setItem('refreshToken', refreshToken)
    },
    CLEAR_TOKENS(state) {
      state.accessToken = null
      state.refreshToken = null
      localStorage.removeItem('accessToken')
      localStorage.removeItem('refreshToken')
    },
    setPageTitle(state, title) {
      state.pageTitle = title
    },
    setLoading(state, isLoading) {
      state.loading = isLoading
    },
    setError(state, error) {
      state.error = error
    },
    SET_ACCOUNT_SELECTION(state, { type, id }) {
      state.accountSelection = { type, id }

      // Save to localStorage
      localStorage.setItem('accountSelection', JSON.stringify({ type, id }))

      // If user exists, update their preferences
      if (state.user) {
        state.user.selected_account_type = type
        state.user.selected_account_id = id
      }
    },
    SET_TABLE_SETTINGS(state, settings) {
      state.tableSettings = { ...state.tableSettings, ...settings }
    },
    INCREMENT_DATA_REFRESH_TRIGGER(state) {
      state.dataRefreshTrigger += 1
    },
    SET_USER_SETTINGS(state, settings) {
      state.userSettings = { ...state.userSettings, ...settings }
    },
    SET_EFFECTIVE_CURRENT_DATE(state, date) {
      state.effectiveCurrentDate = date
    },
    SET_SELECTED_CURRENCY(state, currency) {
      state.selectedCurrency = currency
    },
    SET_NAV_CHART_PARAMS(state, params) {
      state.navChartParams = { ...state.navChartParams, ...params }
    },
    SET_USER(state, user) {
      state.user = user
    },
    SET_INITIALIZED(state, value) {
      state.isInitialized = value
    },
    SET_STATE(state, payload) {
      Object.assign(state, payload)
    },
  },
  actions: {
    async login({ commit, dispatch }, credentials) {
      try {
        const response = await api.login(
          credentials.username,
          credentials.password
        )
        commit('SET_TOKENS', {
          accessToken: response.access,
          refreshToken: response.refresh,
        })
        await dispatch('fetchUserData')
        return { success: true }
      } catch (error) {
        logger.error('Store', 'Login failed from store', error)
        throw error
      }
    },
    async refreshToken({ commit, dispatch, state }) {
      logger.log('Store', 'Refreshing token...')
      try {
        const response = await api.refreshToken(state.refreshToken)
        commit('SET_TOKENS', {
          accessToken: response.access,
          refreshToken: response.refresh || state.refreshToken,
        })
        await dispatch('fetchUserData')
        return { success: true }
      } catch (error) {
        logger.error('Store', 'Token refresh failed', error)
        commit('CLEAR_TOKENS')
        commit('SET_USER', null)
        return { success: false, error: error }
      }
    },
    updatePageTitle({ commit }, title) {
      commit('setPageTitle', title)
    },
    setLoading({ commit }, isLoading) {
      commit('setLoading', isLoading)
    },
    setError({ commit }, error) {
      commit('setError', error)
    },
    async updateAccountSelection({ commit, dispatch, state }, selection) {
      try {
        // First update backend
        await api.updateUserDataForNewAccount({
          type: selection.type,
          id: selection.id,
        })

        // Then update store
        commit('SET_ACCOUNT_SELECTION', {
          type: selection.type,
          id: selection.id,
        })

        logger.log('Store', 'Account selection updated', state.accountSelection)

        // Finally trigger refresh
        dispatch('triggerDataRefresh')
      } catch (error) {
        logger.error('Store', 'Failed to update account selection', error)
        throw error
      }
    },
    triggerDataRefresh({ commit }) {
      commit('INCREMENT_DATA_REFRESH_TRIGGER')
    },
    async fetchEffectiveCurrentDate({ commit }) {
      try {
        const response = await api.getEffectiveCurrentDate()
        commit('SET_EFFECTIVE_CURRENT_DATE', response.effective_current_date)
      } catch (error) {
        logger.error('Store', 'Failed to fetch effective current date', error)
      }
    },
    updateEffectiveCurrentDate({ commit }, date) {
      commit('SET_EFFECTIVE_CURRENT_DATE', date)
    },
    updateTableSettings({ commit }, settings) {
      commit('SET_TABLE_SETTINGS', settings)
    },
    updateNavChartParams({ commit }, params) {
      commit('SET_NAV_CHART_PARAMS', params)
    },
    async logout({ commit }) {
      logger.log('Store', 'Logout action triggered')
      try {
        await api.logout()
      } catch (error) {
        logger.error('Store', 'Error during logout:', error)
      } finally {
        commit('CLEAR_TOKENS')
        commit('SET_USER', null)
        router.push('/login')
      }
    },
    async fetchUserData({ commit }) {
      try {
        const userData = await api.getUserProfile()
        commit('SET_USER', userData)

        // Set account selection from user preferences or localStorage
        const savedSelection = JSON.parse(
          localStorage.getItem('accountSelection')
        )
        const selection = {
          type: userData.selected_account_type || savedSelection?.type || 'all',
          id: userData.selected_account_id || savedSelection?.id || null,
        }
        commit('SET_ACCOUNT_SELECTION', selection)

        return userData
      } catch (error) {
        logger.error('Store', 'Failed to fetch user data:', error)
        throw error
      }
    },
    async initializeApp({ commit, state, dispatch }) {
      const requestId = Date.now()
      logger.log('Store', `[${requestId}] Starting initializeApp`)

      // Check if already initialized or initializing
      if (state.isInitialized) {
        logger.log('Store', `[${requestId}] App already initialized, skipping`)
        return { success: !!state.user }
      }

      if (state.isInitializing) {
        logger.log('Store', `[${requestId}] App already initializing, waiting...`)
        // Wait for initialization to complete instead of starting a new one
        const maxWaitTime = 2000 // 2 seconds max wait
        const startTime = Date.now()
        
        while (state.isInitializing && Date.now() - startTime < maxWaitTime) {
          await new Promise(r => setTimeout(r, 100)) // Wait 100ms and check again
        }
        
        if (state.isInitialized) {
          return { success: !!state.user }
        } else {
          logger.warn('Store', `[${requestId}] Waited too long for initialization, forcing completion`)
          commit('SET_INITIALIZED', true)
          commit('SET_STATE', { isInitializing: false })
          return { success: false }
        }
      }

      try {
        commit('SET_STATE', { isInitializing: true })
        logger.log('Store', `[${requestId}] Set isInitializing=true`)

        const token = localStorage.getItem('accessToken')
        if (!token) {
          logger.log('Store', `[${requestId}] No token found, skipping initialization`)
          return { success: false }
        }

        logger.log('Store', `[${requestId}] Token found, setting tokens and fetching user data`)
        commit('SET_TOKENS', {
          accessToken: token,
          refreshToken: localStorage.getItem('refreshToken'),
        })

        try {
          await dispatch('fetchUserData')
          logger.log('Store', `[${requestId}] User data fetched successfully`)
          return { success: true }
        } catch (error) {
          logger.error('Store', `[${requestId}] Error fetching user data:`, error)
          commit('CLEAR_TOKENS')
          commit('SET_USER', null)
          return { success: false }
        }
      } catch (error) {
        logger.error('Store', `[${requestId}] Initialization error:`, error)
        return { success: false, error }
      } finally {
        logger.log('Store', `[${requestId}] Initialization completed, setting isInitialized=true`)
        commit('SET_INITIALIZED', true)
        commit('SET_STATE', { isInitializing: false })
      }
    },
  },
  getters: {
    isAuthenticated: (state) => {
      return !!state.accessToken && !!state.user
    },
    currentUser: (state) => state.user,
    effectiveCurrentDate: (state) => state.effectiveCurrentDate,
    tableSettings: (state) => state.tableSettings,
    currentAccountSelection: (state) => state.accountSelection,
    isAllAccountsSelected: (state) => state.accountSelection.type === 'all',
    selectedAccountType: (state) => state.accountSelection.type,
    selectedAccountId: (state) => state.accountSelection.id,
  },
})
