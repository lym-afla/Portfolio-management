import { createStore } from 'vuex'
import axios from 'axios'

export default createStore({
  state: {
    token: localStorage.getItem('token') || null,
    user: null
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
    }
  },
  actions: {
    async login({ commit }, credentials) {
      try {
        const response = await axios.post('/users/api/login/', credentials)
        const token = response.data.token
        localStorage.setItem('token', token)
        commit('setToken', token)
        commit('setUser', response.data)
        return true
      } catch (error) {
        console.error('Login failed', error)
        return false
      }
    },
    logout({ commit }) {
      localStorage.removeItem('token')
      commit('logout')
    },
    async register({ commit }, credentials) {
      try {
        const response = await axios.post('/users/api/register/', credentials)
        const token = response.data.token
        localStorage.setItem('token', token)
        commit('setToken', token)
        commit('setUser', response.data)
        return true
      } catch (error) {
        console.error('Registration failed', error)
        return false
      }
    }
  },
  getters: {
    isAuthenticated: state => !!state.token
  }
})