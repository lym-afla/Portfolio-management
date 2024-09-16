<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="pa-4">
          <v-card-title class="headline">Register</v-card-title>
          <v-card-text>
            <RegisterForm 
              ref="registerForm"
              @register="handleRegister" 
              :loading="loading" 
              :serverErrors="errors"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <span>Already have an account? <router-link to="/login">Login</router-link></span>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Success Dialog -->
    <v-dialog v-model="showSuccessDialog" max-width="400">
      <v-card>
        <v-card-title class="headline">Registration Successful</v-card-title>
        <v-card-text>
          {{ successMessage }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" text @click="redirectToLogin">
            Go to Login
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
import { ref, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '@/services/api'
import RegisterForm from '@/components/RegisterForm.vue'

export default {
  name: 'RegisterPage',
  components: {
    RegisterForm
  },
  setup() {
    const loading = ref(false)
    const successMessage = ref('')
    const showSuccessDialog = ref(false)
    const router = useRouter()
    const registerForm = ref(null)
    const errors = ref({})

    const handleRegister = async (credentials) => {
      console.log('Handling registration with credentials:', credentials)
      loading.value = true
      errors.value = {}

      try {
        await register(credentials.username, credentials.email, credentials.password, credentials.password2)
        successMessage.value = 'Registration successful. You can now log in to your account.'
        showSuccessDialog.value = true
      } catch (err) {
        console.error('Registration error:', err)
        if (err.response && err.response.data) {
          errors.value = err.response.data
        } else {
          errors.value = { general: 'An error occurred during registration.' }
        }
      } finally {
        loading.value = false
      }
    }

    const redirectToLogin = () => {
      router.push('/login')
    }

    onBeforeUnmount(() => {
      errors.value = {}
    })

    return { 
      loading, 
      handleRegister, 
      registerForm, 
      successMessage, 
      showSuccessDialog, 
      redirectToLogin,
      errors
    }
  },
  mounted() {
    this.$emit('update-page-title', ''); // Clear the page title for register page
  }
}
</script>

<style scoped>
.v-card-actions a {
  text-decoration: none;
  color: #1976D2;
}
</style>