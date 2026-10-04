<template>
  <v-container class="fill-height auth-surface" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="5" lg="4">
        <WorkspacePage title="Login" description="Sign in to your portfolio workspace.">
          <LoginForm
            ref="loginForm"
            @submit="handleLogin"
            :loading="loading"
          />
          <p class="workspace-meta mt-4 mb-0 text-center">
            Don't have an account?
            <router-link to="/register">Register</router-link>
          </p>
        </WorkspacePage>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LoginForm from '@/components/LoginForm.vue'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import logger from '@/utils/logger'

// Shape of the credentials emitted by LoginForm's @submit event.
interface LoginCredentials {
  username: string
  password: string
}

// Shape of the error body thrown by authStore.login (DRF error response).
interface LoginError {
  non_field_errors?: string[]
  [key: string]: unknown
}

// Methods exposed by LoginForm via defineExpose.
interface LoginFormInstance {
  setErrors: (errors: string | Record<string, unknown>) => void
  clearError: (field: string) => void
}

const loading = ref(false)
const router = useRouter()
const loginForm = ref<LoginFormInstance | null>(null)
const authStore = useAuthStore()

const handleLogin = async (credentials: LoginCredentials) => {
  logger.log('Unknown', 'Handling login with credentials:', credentials)
  loading.value = true

  try {
    const result = await authStore.login(credentials)
    if (result.success) {
      logger.log('Unknown', 'Login successful from LoginPage.vue')
      router.push('/profile')
    }
  } catch (error) {
    logger.log('Unknown', 'Login failed from LoginPage.vue', error)
    const loginError = error as LoginError
    if (loginError.non_field_errors) {
      logger.log('Unknown', 'Non-field errors:', loginError.non_field_errors)
      loginForm.value?.setErrors(loginError.non_field_errors[0])
    } else if (error) {
      logger.log('Unknown', 'Field errors:', error)
      loginForm.value?.setErrors(error as Record<string, unknown>)
    } else {
      logger.log('Unknown', 'Unknown error')
      loginForm.value?.setErrors(
        'An unknown error occurred. Please try again.'
      )
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-surface :deep(a) {
  text-decoration: none;
  color: rgb(var(--v-theme-primary));
}
</style>
