<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field
      v-model="username"
      label="Username"
      required
      :error-messages="fieldErrors.username"
    ></v-text-field>
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      required
      :error-messages="fieldErrors.password"
    ></v-text-field>
    <v-btn type="submit" color="primary" block :loading="loading">Login</v-btn>
    <v-alert v-if="generalError" type="error" class="mt-3">{{ generalError }}</v-alert>
  </v-form>
</template>

<script>
import { ref, reactive } from 'vue'

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

    const submitForm = () => {
      // Clear previous errors
      fieldErrors.username = []
      fieldErrors.password = []
      generalError.value = ''

      const credentials = { username: username.value, password: password.value }
      console.log('Submitting form with data:', credentials)
      emit('submit', credentials)
    }

    const setErrors = (errors) => {
      console.log('Setting errors:', errors)
      if (typeof errors === 'string') {
        generalError.value = errors
      } else if (typeof errors === 'object') {
        Object.keys(errors).forEach(field => {
          if (field in fieldErrors) {
            fieldErrors[field] = Array.isArray(errors[field]) ? errors[field] : [errors[field]]
          } else if (field === 'non_field_errors') {
            generalError.value = Array.isArray(errors[field]) ? errors[field][0] : errors[field]
          } else {
            generalError.value = errors[field]
          }
        })
      }
      console.log('Field errors after setting:', fieldErrors)
      console.log('General error after setting:', generalError.value)
    }

    return {
      username,
      password,
      fieldErrors,
      generalError,
      submitForm,
      setErrors
    }
  }
}
</script>