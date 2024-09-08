import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import App from './App.vue'
import router from './router'
import store from './store'
import axios from 'axios'
import './assets/fonts.css'
import './plugins/vee-validate';

axios.defaults.xsrfCookieName = 'csrftoken'
axios.defaults.xsrfHeaderName = 'X-CSRFToken'

axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    console.log('Token from localStorage:', token);
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
      console.log('Authorization header set:', config.headers['Authorization']);
    } else {
      console.log('No token found in localStorage');
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

axios.interceptors.response.use(
  (response) => response,
  (error) => {
    console.log('Response error:', error.response);
    if (error.response && error.response.status === 401) {
      console.log('401 Unauthorized error detected');
      store.commit('logout')
      router.push('/login')
    }
    return Promise.reject(error)
  }
);

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