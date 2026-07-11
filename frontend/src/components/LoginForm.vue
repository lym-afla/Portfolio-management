<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field
      v-model="username"
      label="Username"
      autocomplete="username"
      required
      :error-messages="fieldErrors.username"
      @input="clearError('username')"
    />
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      autocomplete="current-password"
      required
      :error-messages="fieldErrors.password"
      @input="clearError('password')"
    />
    <v-btn
      type="submit"
      color="primary"
      block
      :loading="loading"
      :disabled="loading"
      >Login</v-btn
    >
    <v-alert v-if="generalError" type="error" class="mt-3">{{
      generalError
    }}</v-alert>
  </v-form>
</template>

<script>
import { ref, reactive } from 'vue'
import logger from '@/utils/logger'

export default {
  props: {
    loading: Boolean,
  },
  emits: ['submit'],
  setup(props, { emit }) {
    const username = ref('')
    const password = ref('')
    const fieldErrors = reactive({
      username: [],
      password: [],
    })
    const generalError = ref('')

    const clearError = (field) => {
      fieldErrors[field] = []
      generalError.value = ''
    }

    const submitForm = () => {
      // Clear previous errors
      fieldErrors.username = []
      fieldErrors.password = []
      generalError.value = ''

      const credentials = { username: username.value, password: password.value }
      logger.log('Unknown', 'Submitting form with data:', credentials)
      emit('submit', credentials)
    }

    const setErrors = (errors) => {
      logger.log('Unknown', 'Setting errors:', errors)
      if (typeof errors === 'string') {
        if (errors.includes('Proxy')) {
          generalError.value =
            'Proxy error. Please check your internet connection. Or application server is down.'
        } else {
          generalError.value = errors
        }
      } else if (typeof errors === 'object') {
        Object.keys(errors).forEach((field) => {
          if (field in fieldErrors) {
            fieldErrors[field] = Array.isArray(errors[field])
              ? errors[field]
              : [errors[field]]
          } else if (field === 'non_field_errors') {
            generalError.value = Array.isArray(errors[field])
              ? errors[field][0]
              : errors[field]
          } else {
            generalError.value = errors[field]
          }
        })
      }
      logger.log('Unknown', 'Field errors after setting:', fieldErrors)
      logger.log('Unknown', 'General error after setting:', generalError.value)
    }

    return {
      username,
      password,
      fieldErrors,
      generalError,
      submitForm,
      setErrors,
      clearError,
    }
  },
}
</script>
