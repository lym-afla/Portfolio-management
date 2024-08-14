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
            <v-spacer></v-spacer>
            <span>Don't have an account? <router-link to="/register">Register</router-link></span>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import LoginForm from '@/components/LoginForm.vue'

export default {
  name: 'LoginPage',
  components: {
    LoginForm
  },
  setup() {
    const loading = ref(false)
    const router = useRouter()
    const loginForm = ref(null)

    const handleLogin = async (credentials) => {
      console.log('Handling login with credentials:', credentials)
      loading.value = true

      try {
        const response = await axios.post('/users/api/login/', credentials)
        console.log('Login response:', response.data)
        if (response.data.token) {
          localStorage.setItem('token', response.data.token)
          router.push('/dashboard')
        } else {
          console.log('Login failed, no token received')
          loginForm.value.setErrors('Login failed. Please try again.')
        }
      } catch (err) {
        console.error('Login error:', err)
        console.error('Error response:', err.response?.data)
        if (err.response?.data?.non_field_errors) {
          console.log('Non-field errors:', err.response.data.non_field_errors)
          loginForm.value.setErrors(err.response.data.non_field_errors[0])
        } else if (err.response?.data) {
          console.log('Field errors:', err.response.data)
          loginForm.value.setErrors(err.response.data)
        } else {
          console.log('Unknown error')
          loginForm.value.setErrors('An unknown error occurred. Please try again.')
        }
      } finally {
        loading.value = false
      }
    }

    return { loading, handleLogin, loginForm }
  }
}
</script>

<style scoped>
.v-card-actions a {
  text-decoration: none;
  color: #1976D2;
}
</style>