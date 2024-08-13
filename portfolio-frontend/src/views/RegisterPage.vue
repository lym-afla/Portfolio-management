<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="pa-4">
          <v-card-title class="headline">Register</v-card-title>
          <v-card-text>
            <RegisterForm @register="handleRegister" :loading="loading" :error="error" />
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <span>Already have an account? <router-link to="/login">Login</router-link></span>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
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
    const loading = ref(false)
    const router = useRouter()
    const store = useStore()

    const handleRegister = async (credentials) => {
      loading.value = true
      error.value = ''

      try {
        const success = await store.dispatch('register', credentials)
        if (success) {
          router.push('/dashboard')
        } else {
          error.value = 'Registration failed. Please try again.'
        }
      } catch (err) {
        error.value = 'An error occurred during registration.'
      } finally {
        loading.value = false
      }
    }

    return { error, loading, handleRegister }
  }
}
</script>

<style scoped>
.v-card-actions a {
  text-decoration: none;
  color: #1976D2;
}
</style>