import { config } from '@vue/test-utils'
import { beforeEach } from 'vitest'

import { createMemoryStorage } from './helpers/memoryStorage'

beforeEach(() => {
  Object.defineProperties(globalThis, {
    localStorage: {
      configurable: true,
      value: createMemoryStorage(),
    },
    sessionStorage: {
      configurable: true,
      value: createMemoryStorage(),
    },
  })
})

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
