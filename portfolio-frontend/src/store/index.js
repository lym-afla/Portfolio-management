import { createStore } from 'vuex'
import axios from 'axios'

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
        const response = await axios.post('/users/api/login/', credentials)
        const token = response.data.token
        localStorage.setItem('token', token)
        commit('setToken', token)
        commit('setUser', response.data)
        return { success: true }
      } catch (error) {
        console.error('Login failed', error)
        return { success: false, error: error.response ? error.response.data : 'Login failed' }
      }
    },
    async logout({ commit }) {
      try {
        await axios.post('/users/api/logout/');
        localStorage.removeItem('token');
        commit('logout');
        return { success: true };
      } catch (error) {
        console.error('Logout failed:', error);
        localStorage.removeItem('token');
        commit('logout');
        return { success: false, error: 'Logout failed' };
      }
    },
    async register(_, credentials) {
      try {
        await axios.post('/users/api/register/', credentials)
        return { success: true, message: 'Registration successful. Please log in.' }
      } catch (error) {
        console.error('Registration failed', error)
        return { success: false, error: error.response ? error.response.data : 'Registration failed' }
      }
    },
    async deleteAccount({ commit }) {
      try {
        await axios.delete('/users/api/delete-account/')
        localStorage.removeItem('token')
        commit('logout')
        return { success: true, message: 'Account successfully deleted.' }
      } catch (error) {
        console.error('Account deletion failed', error)
        return { success: false, error: error.response ? error.response.data : 'Account deletion failed' }
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
    setCustomBrokers({ commit }, brokers) {
      commit('SET_CUSTOM_BROKERS', brokers)
    },
    triggerDataRefresh({ commit }) {
      commit('INCREMENT_DATA_REFRESH_TRIGGER')
    },
  },
  getters: {
    isAuthenticated: state => !!state.token
  }
})