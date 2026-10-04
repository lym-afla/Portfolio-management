<template>
  <v-container class="fill-height auth-surface" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="5" lg="4">
        <WorkspacePage title="Register" description="Create a new portfolio workspace account.">
          <RegisterForm
            ref="registerForm"
            @register="handleRegister"
            :loading="loading"
            :errors="errors"
          />
          <p class="workspace-meta mt-4 mb-0 text-center">
            Already have an account?
            <router-link to="/login">Login</router-link>
          </p>
        </WorkspacePage>
      </v-col>
    </v-row>

    <!-- Success Dialog -->
    <v-dialog v-model="showSuccessDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Registration Successful</v-card-title>
        <v-card-text>
          {{ successMessage }}
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="tonal" @click="redirectToLogin">
            Go to Login
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '@/services/api'
import RegisterForm from '@/components/RegisterForm.vue'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import logger from '@/utils/logger'

const emit = defineEmits(['update-page-title'])

const loading = ref(false)
const successMessage = ref('')
const showSuccessDialog = ref(false)
const router = useRouter()
const registerForm = ref(null)
const errors = ref({})

const handleRegister = async (credentials) => {
  logger.log(
    'Unknown',
    'Handling registration with credentials:',
    credentials
  )
  loading.value = true
  errors.value = {}

  try {
    const response = await register(
      credentials.username,
      credentials.email,
      credentials.password,
      credentials.password2
    )
    successMessage.value =
      response.message ||
      'Registration successful. You can now log in to your account.'
    showSuccessDialog.value = true
  } catch (err) {
    logger.error('Unknown', '[RegisterPage] Registration error:', err)
    if (typeof err === 'object' && err !== null) {
      errors.value = err
    } else {
      errors.value = { general: [err.toString()] }
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

onMounted(() => {
  emit('update-page-title', '') // Clear the page title for register page
})
</script>

<style scoped>
.auth-surface :deep(a) {
  text-decoration: none;
  color: rgb(var(--v-theme-primary));
}
</style>
