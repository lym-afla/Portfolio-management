import { createStore } from 'vuex'
import * as api from '@/services/api'
import router from '@/router'
// import axios from 'axios'

export default createStore({
  state: {
    accessToken: localStorage.getItem('accessToken') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    user: null,
    pageTitle: '',
    loading: false,
    error: null,
    customBrokerSelection: null,
    dataRefreshTrigger: 0,
    selectedBroker: null,
    effectiveCurrentDate: null,
    selectedCurrency: null,
    tableSettings: {
      dateFrom: null,
      dateTo: null,
      timespan: 'ytd', // Set default timespan to 'ytd'
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
      dateTo: null
    }
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
    SET_CUSTOM_BROKER_SELECTION(state, broker_choices) {
      state.customBrokerSelection = broker_choices
    },
    SET_TABLE_SETTINGS(state, settings) {
      state.tableSettings = { ...state.tableSettings, ...settings }
    },
    INCREMENT_DATA_REFRESH_TRIGGER(state) {
      state.dataRefreshTrigger += 1
    },
    // SET_SELECTED_BROKER(state, broker) {
    //   state.selectedBroker = broker
    // },
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
    }
  },
  actions: {
    async login({ commit, dispatch }, credentials) {
      try {
        const response = await api.login(credentials.username, credentials.password)
        commit('SET_TOKENS', {
          accessToken: response.access,
          refreshToken: response.refresh
        })
        await dispatch('fetchUserData')
        return { success: true }
      } catch (error) {
        console.error('Login failed from store', error)
        throw error
      }
    },
    async refreshToken({ commit, dispatch, state }) {
      console.log('Refreshing token...')
      try {
        const response = await api.refreshToken(state.refreshToken)
        commit('SET_TOKENS', {
          accessToken: response.access,
          refreshToken: response.refresh || state.refreshToken
        })
        await dispatch('fetchUserData')
        return { success: true }
      } catch (error) {
        console.error('Token refresh failed', error)
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
    async setCustomBrokers({ commit }) {
      try {
        const broker_choices = await api.getBrokerChoices()
        commit('SET_CUSTOM_BROKER_SELECTION', broker_choices)
      } catch (error) {
        console.error('Failed to fetch brokers', error)
        commit('setError', 'Failed to fetch brokers')
      }
    },
    // updateSelectedBroker({ commit }, broker) {
    //   commit('SET_SELECTED_BROKER', broker)
    // },
    triggerDataRefresh({ commit }) {
      commit('INCREMENT_DATA_REFRESH_TRIGGER')
    },
    async fetchEffectiveCurrentDate({ commit }) {
      try {
        const response = await api.getEffectiveCurrentDate()
        commit('SET_EFFECTIVE_CURRENT_DATE', response.effective_current_date)
      } catch (error) {
        console.error('Failed to fetch effective current date', error)
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
      console.log('Logout action triggered')
      try {
        await api.logout()
      } catch (error) {
        console.error('Error during logout:', error)
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
      } catch (error) {
        console.error('Failed to fetch user data', error)
        throw error
      }
    },
    async initializeApp({ commit, dispatch, state }) {
      if (state.accessToken && !state.user) {
        try {
          await dispatch('fetchUserData')
          return { success: true }
        } catch (error) {
          console.error('Failed to initialize app:', error)
          const refreshResult = await dispatch('refreshToken')
          if (!refreshResult.success) {
            commit('CLEAR_TOKENS')
            commit('SET_USER', null)
            return { success: false }
          }
          return { success: true }
        }
      }
      return { success: !!state.user }
    }
  },
  getters: {
    isAuthenticated: state => !!state.accessToken && !!state.user,
    currentUser: state => state.user,
    effectiveCurrentDate: state => state.effectiveCurrentDate,
    tableSettings: state => state.tableSettings,
  }
})
