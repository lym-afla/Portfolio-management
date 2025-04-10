import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import App from './App.vue'
import router from './router'
import store from './store'
import './assets/fonts.css'
import './plugins/vee-validate'
import logger from './utils/logger'

const vuetify = createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi',
  },
  theme: {
    defaultTheme: 'light',
    themes: {
      light: {
        dark: false,
        variables: {
          fontFamily: 'var(--system-font)',
        },
      },
    },
  },
})

// Initialize logger
logger.log('App', 'Application starting...')

// Set debug based on environment
if (process.env.NODE_ENV !== 'production') {
  logger.setDebugEnabled(true)
  logger.info('App', `Running in ${process.env.NODE_ENV} mode`)
} else {
  logger.setDebugEnabled(false)
  // This won't show in production unless debug is manually enabled
  logger.info('App', 'Running in production mode')
}

// Create and mount the app
const app = createApp(App)
app.use(vuetify)
app.use(store)
app.use(router)

// Make logger available globally for debugging in development
if (process.env.NODE_ENV !== 'production') {
  window.$logger = logger
}

app.mount('#app')

// Report that app is mounted
logger.log('App', 'Application mounted')
