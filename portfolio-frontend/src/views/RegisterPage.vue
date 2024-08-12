<template>
  <div class="register-page">
    <h1>Register</h1>
    <RegisterForm @register="handleRegister" />
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      Already have an account? <router-link to="/login">Login</router-link>
    </p>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStore } from 'vuex'
import RegisterForm from '@/components/RegisterForm.vue'

export default {
  name: 'RegisterPage',
  components: {
    RegisterForm
  },
  setup() {
    const error = ref('')
    const router = useRouter()
    const store = useStore()

    const handleRegister = async (credentials) => {
      try {
        const success = await store.dispatch('register', credentials)
        if (success) {
          router.push('/dashboard')
        } else {
          error.value = 'Registration failed. Please try again.'
        }
      } catch (err) {
        error.value = 'An error occurred during registration.'
      }
    }

    return { error, handleRegister }
  }
}
</script>