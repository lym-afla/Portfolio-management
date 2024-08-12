<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field v-model="username" label="Username" required></v-text-field>
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      required
    ></v-text-field>
    <v-btn type="submit" color="primary" block :loading="loading">Login</v-btn>
    <v-alert v-if="error" type="error" class="mt-3">{{ error }}</v-alert>
  </v-form>
</template>

<script>
import { ref, inject } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

export default {
  setup() {
    const username = ref('')
    const password = ref('')
    const loading = ref(false)
    const error = ref(null)
    const router = useRouter()
    const setUser = inject('setUser')

    const submitForm = async () => {
      loading.value = true
      error.value = null

      try {
        const response = await axios.post('/users/api/login/', {
          username: username.value,
          password: password.value,
        })

        console.log('Login successful', response.data)
        
        localStorage.setItem('token', response.data.token)
        
        setUser({
          id: response.data.user_id,
          email: response.data.email,
          username: username.value,
        })
        
        router.push('/dashboard')
      } catch (err) {
        console.error('Login error', err)
        error.value = 'Invalid login credentials. Please try again.'
      } finally {
        loading.value = false
      }
    }

    return {
      username,
      password,
      loading,
      error,
      submitForm
    }
  }
}
</script>