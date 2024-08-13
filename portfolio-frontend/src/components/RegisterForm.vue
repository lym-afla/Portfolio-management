<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field
      v-model="username"
      label="Username"
      required
      :error-messages="errors.username"
      @input="clearError('username')"
    ></v-text-field>
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      required
      :error-messages="errors.email"
      @input="clearError('email')"
    ></v-text-field>
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      required
      :error-messages="errors.password"
      @input="clearError('password')"
    ></v-text-field>
    <v-text-field
      v-model="confirmPassword"
      label="Confirm Password"
      type="password"
      required
      :error-messages="errors.confirmPassword"
      @input="clearError('confirmPassword')"
    ></v-text-field>
    <v-btn type="submit" color="primary" block :loading="loading">Register</v-btn>
    <v-alert v-if="errors.general" type="error" class="mt-3">{{ errors.general }}</v-alert>
  </v-form>
</template>

<script>
import { ref, reactive } from 'vue'

export default {
  props: {
    loading: Boolean,
  },
  emits: ['register'],
  setup(props, { emit }) {
    const username = ref('')
    const email = ref('')
    const password = ref('')
    const confirmPassword = ref('')
    const errors = reactive({
      username: [],
      email: [],
      password: [],
      confirmPassword: [],
      general: null,
    })

    const clearError = (field) => {
      errors[field] = []
      errors.general = null
    }

    const submitForm = () => {
      if (password.value !== confirmPassword.value) {
        errors.confirmPassword = ['Passwords do not match']
        return
      }
      emit('register', {
        username: username.value,
        email: email.value,
        password: password.value,
      })
    }

    const setErrors = (newErrors) => {
      Object.keys(errors).forEach(key => {
        errors[key] = []
      })
      errors.general = null
      
      if (typeof newErrors === 'string') {
        errors.general = newErrors
      } else if (typeof newErrors === 'object' && newErrors !== null) {
        Object.keys(newErrors).forEach(field => {
          if (field in errors) {
            errors[field] = Array.isArray(newErrors[field]) ? newErrors[field] : [newErrors[field]]
          } else {
            errors.general = newErrors[field]
          }
        })
      }
    }

    return {
      username,
      email,
      password,
      confirmPassword,
      errors,
      submitForm,
      clearError,
      setErrors
    }
  }
}
</script>