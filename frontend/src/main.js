import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import App from './App.vue'
import router from './router'
import axiosInstance, { refreshTokenWithEffectiveDate, getAuthSessionEpoch } from './config/axiosConfig'
import { configureApiTransport, configurePortfolioReadGuard } from './services/http/client'
import { configurePortfolioContextBackend, createPortfolioContextBackend } from './services/api/context'
import { usePortfolioContextStore } from './stores/portfolioContext'
import { createPinia } from 'pinia'
import './assets/fonts.css'
import './plugins/vee-validate'
import logger from './utils/logger'
import { createAppTheme } from './theme'
import { appIcons } from './plugins/icons'

const vuetify = createVuetify({
  components,
  directives,
  icons: appIcons,
  theme: createAppTheme(),
})

// Initialize logger
logger.log('App', 'Application starting...')

// Set debug based on environment
if (import.meta.env.DEV) {
  logger.setDebugEnabled(true)
  logger.info('App', `Running in ${import.meta.env.MODE} mode`)
} else {
  logger.setDebugEnabled(false)
  // This won't show in production unless debug is manually enabled
  logger.info('App', 'Running in production mode')
}

// Create and mount the app
const app = createApp(App)
app.use(vuetify)
app.use(createPinia())
configureApiTransport(axiosInstance)
configurePortfolioReadGuard(() => usePortfolioContextStore().canRead)
configurePortfolioContextBackend(createPortfolioContextBackend(refreshTokenWithEffectiveDate, getAuthSessionEpoch))
app.use(router)

// Make debugging tools available globally for debugging in development
if (import.meta.env.DEV) {
  window.$logger = logger
  import('./utils/authDebugConsole')
  import('./utils/authDebug').then(module => { window.$authDebug = module.default })
  import('./utils/axiosDebug').then((module) => {
    window.$debugAxios = module.debugAxiosConfiguration
  })
}

app.mount('#app')

// Report that app is mounted
logger.log('App', 'Application mounted')
