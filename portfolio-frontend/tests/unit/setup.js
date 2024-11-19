import { config } from '@vue/test-utils'

// Mock Vuetify
const vuetify = {
  install(app) {
    app.config.globalProperties.$vuetify = {
      theme: {
        global: {
          name: 'light'
        }
      }
    }
  }
}

// Global plugins config
config.global.plugins = [vuetify]

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} 