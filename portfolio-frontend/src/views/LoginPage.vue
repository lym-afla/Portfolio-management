<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="pa-4">
          <v-card-title class="headline">Login</v-card-title>
          <v-card-text>
            <LoginForm
              ref="loginForm"
              @submit="handleLogin"
              :loading="loading"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <span
              >Don't have an account?
              <router-link to="/register">Register</router-link></span
            >
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
// import axios from 'axios'
import store from '@/store'
import LoginForm from '@/components/LoginForm.vue'

export default {
  name: 'LoginPage',
  components: {
    LoginForm,
  },
  setup() {
    const loading = ref(false)
    const router = useRouter()
    const loginForm = ref(null)

    const handleLogin = async (credentials) => {
      console.log('Handling login with credentials:', credentials)
      loading.value = true

      try {
        const result = await store.dispatch('login', credentials)
        console.log(
          '[LoginPage.vue] Token set in the store:',
          store.state.accessToken
        )
        console.log(
          '[LoginPage.vue] Token from localStorage:',
          localStorage.getItem('accessToken')
        )
        if (result.success) {
          console.log('Login successful from LoginPage.vue')
          router.push('/profile')
        }
      } catch (error) {
        console.log('Login failed from LoginPage.vue', error)
        if (error.non_field_errors) {
          console.log('Non-field errors:', error.non_field_errors)
          loginForm.value.setErrors(error.non_field_errors[0])
        } else if (error) {
          console.log('Field errors:', error)
          loginForm.value.setErrors(error)
        } else {
          console.log('Unknown error')
          loginForm.value.setErrors(
            'An unknown error occurred. Please try again.'
          )
        }
      } finally {
        loading.value = false
      }
    }

    return { loading, handleLogin, loginForm }
  },
}
</script>

<style scoped>
.v-card-actions a {
  text-decoration: none;
  color: #1976d2;
}
</style>
