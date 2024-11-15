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

createApp(App)
  .use(vuetify)
  .use(router)
  .use(store)
  .mount('#app')