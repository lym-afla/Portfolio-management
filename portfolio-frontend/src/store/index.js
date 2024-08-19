import { createStore } from 'vuex'
import * as api from '@/services/api'

export default createStore({
  state: {
    token: localStorage.getItem('token') || null,
    user: null,
    pageTitle: '',
    loading: false,
    error: null,
    customBrokerSelection: null,
    dataRefreshPayload: null,
    dataRefreshTrigger: 0,
    selectedBroker: null,
    effectiveCurrentDate: null,
    selectedYear: 'All-time',
    currentPage: 1,
    itemsPerPage: 25,
    itemsPerPageOptions: [10, 25, 50, 100],
    search: '',
    sortBy: {},
  },
  mutations: {
    setToken(state, token) {
      state.token = token
    },
    setUser(state, user) {
      state.user = user
    },
    logout(state) {
      state.token = null
      state.user = null
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
    SET_DATA_REFRESH_PAYLOAD(state, payload) {
      state.dataRefreshPayload = payload
    },
    INCREMENT_DATA_REFRESH_TRIGGER(state) {
      state.dataRefreshTrigger += 1
    },
    SET_SELECTED_BROKER(state, broker) {
      state.selectedBroker = broker
    },
    SET_USER_SETTINGS(state, settings) {
      state.userSettings = { ...state.userSettings, ...settings }
    },
    SET_EFFECTIVE_CURRENT_DATE(state, date) {
      state.effectiveCurrentDate = date
    },
    SET_SELECTED_YEAR(state, year) {
      state.selectedYear = year
    },
    SET_ITEMS_PER_PAGE_OPTIONS(state, options) {
      state.itemsPerPageOptions = options
    },
    SET_CURRENT_PAGE(state, page) {
      state.currentPage = page
    },
    SET_ITEMS_PER_PAGE(state, itemsPerPage) {
      state.itemsPerPage = itemsPerPage
    },
    SET_SEARCH(state, search) {
      state.search = search
    },
    SET_SORT_BY(state, sortBy) {
      state.sortBy = sortBy
    },
  },
  actions: {
    async login({ commit }, credentials) {
      try {
        const response = await api.login(credentials.username, credentials.password)
        const token = response.token
        localStorage.setItem('token', token)
        commit('setToken', token)
        commit('setUser', response)
        return { success: true }
      } catch (error) {
        console.error('Login failed', error)
        return { success: false, error: error }
      }
    },
    async logout({ commit }) {
      try {
        await api.logout()
        localStorage.removeItem('token')
        commit('logout')
        return { success: true }
      } catch (error) {
        console.error('Logout failed:', error)
        localStorage.removeItem('token')
        commit('logout')
        return { success: false, error: 'Logout failed' }
      }
    },
    async register(_, credentials) {
      try {
        await api.register(credentials.username, credentials.email, credentials.password)
        return { success: true, message: 'Registration successful. Please log in.' }
      } catch (error) {
        console.error('Registration failed', error)
        return { success: false, error: error }
      }
    },
    async deleteAccount({ commit }) {
      try {
        await api.deleteAccount()
        localStorage.removeItem('token')
        commit('logout')
        return { success: true, message: 'Account successfully deleted.' }
      } catch (error) {
        console.error('Account deletion failed', error)
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
    updateSelectedBroker({ commit }, broker) {
      commit('SET_SELECTED_BROKER', broker)
    },
    triggerDataRefresh({ commit }, payload) {
      commit('SET_DATA_REFRESH_PAYLOAD', payload)
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
    updateSelectedYear({ commit }, year) {
      commit('SET_SELECTED_YEAR', year)
    },
    updateItemsPerPageOptions({ commit }, options) {
      commit('SET_ITEMS_PER_PAGE_OPTIONS', options)
    },
    updateCurrentPage({ commit }, page) {
      commit('SET_CURRENT_PAGE', page)
    },
    updateItemsPerPage({ commit }, itemsPerPage) {
      commit('SET_ITEMS_PER_PAGE', itemsPerPage)
    },
    updateSearch({ commit }, search) {
      commit('SET_SEARCH', search)
    },
    updateSortBy({ commit }, sortBy) {
      commit('SET_SORT_BY', sortBy)
    },
  },
  getters: {
    isAuthenticated: state => !!state.token,
    effectiveCurrentDate: state => state.effectiveCurrentDate,
  }
})