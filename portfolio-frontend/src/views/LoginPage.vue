<template>
  <div class="login-page">
    <h1>Login</h1>
    <LoginForm @login="handleLogin" />
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      Don't have an account? <router-link to="/register">Register</router-link>
    </p>
  </div>
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
    const error = ref('')
    const router = useRouter()

    const handleLogin = async (credentials) => {
      try {
        const response = await axios.post('/users/api/login/', credentials)
        localStorage.setItem('token', response.data.token)
        router.push('/dashboard')
      } catch (err) {
        error.value = 'Invalid login credentials. Please try again.'
      }
    }

    return { error, handleLogin }
  },
}
</script>