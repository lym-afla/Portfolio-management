<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field
      v-model="username"
      label="Username"
      required
      :error-messages="formErrors.username"
      @input="clearError('username')"
      autocomplete="username"
    ></v-text-field>
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      required
      :error-messages="formErrors.email"
      @input="clearError('email')"
    ></v-text-field>
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      required
      :error-messages="formErrors.password"
      @input="clearError('password')"
      autocomplete="new-password"
    ></v-text-field>
    <v-text-field
      v-model="password2"
      label="Confirm Password"
      type="password"
      required
      :error-messages="formErrors.password2"
      @input="clearError('password2')"
    ></v-text-field>
    <v-btn type="submit" color="primary" block :loading="loading">Register</v-btn>
    <v-alert v-if="formErrors.general" type="error" class="mt-3">{{ formErrors.general }}</v-alert>
  </v-form>
</template>

<script>
import { ref, reactive, watch } from 'vue'

export default {
  props: {
    loading: Boolean,
    serverErrors: {
      type: Object,
      default: () => ({})
    }
  },
  emits: ['register'],
  setup(props, { emit }) {
    const username = ref('')
    const email = ref('')
    const password = ref('')
    const password2 = ref('')
    const formErrors = reactive({
      username: [],
      email: [],
      password: [],
      password2: [],
      general: null,
    })

    watch(() => props.serverErrors, (newErrors) => {
      Object.keys(formErrors).forEach(key => {
        formErrors[key] = Array.isArray(newErrors[key]) ? newErrors[key] : [newErrors[key]]
      })
      if (newErrors.general) {
        formErrors.general = newErrors.general
      }
    }, { deep: true })

    const clearError = (field) => {
      formErrors[field] = []
      formErrors.general = null
    }

    const submitForm = () => {
      emit('register', {
        username: username.value,
        email: email.value,
        password: password.value,
        password2: password2.value
      })
    }

    return {
      username,
      email,
      password,
      password2,
      formErrors,
      submitForm,
      clearError,
    }
  }
}
</script>