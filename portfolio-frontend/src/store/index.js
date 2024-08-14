import { createStore } from 'vuex'
import * as api from '@/services/api'

export default createStore({
  state: {
    token: localStorage.getItem('token') || null,
    user: null,
    pageTitle: '',
    loading: false,
    error: null,
    customBrokers: null,
    dataRefreshTrigger: 0,
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
    SET_CUSTOM_BROKERS(state, brokers) {
      state.customBrokers = brokers
    },
    INCREMENT_DATA_REFRESH_TRIGGER(state) {
      state.dataRefreshTrigger += 1
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
        const brokers = await api.getBrokers()
        commit('SET_CUSTOM_BROKERS', brokers)
      } catch (error) {
        console.error('Failed to fetch brokers', error)
        commit('setError', 'Failed to fetch brokers')
      }
    },
    triggerDataRefresh({ commit }) {
      commit('INCREMENT_DATA_REFRESH_TRIGGER')
    },
    async changePassword(_, passwordData) {
      try {
        return await api.changeUserPassword(passwordData)
      } catch (error) {
        console.error('Password change failed', error)
        throw error
      }
    },
    async fetchUserProfile() {
      try {
        return await api.getUserProfile()
      } catch (error) {
        console.error('Fetching user profile failed', error)
        throw error
      }
    },
  },
  getters: {
    isAuthenticated: state => !!state.token
  }
})