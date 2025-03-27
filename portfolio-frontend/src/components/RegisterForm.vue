<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field
      v-model="username"
      label="Username"
      :error-messages="formErrors.username"
      @input="clearError('username')"
      autocomplete="username"
    />
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      :error-messages="formErrors.email"
      @input="clearError('email')"
    />
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      :error-messages="formErrors.password"
      @input="clearError('password')"
      autocomplete="new-password"
    />
    <v-text-field
      v-model="password2"
      label="Confirm Password"
      type="password"
      :error-messages="formErrors.password2"
      @input="clearError('password2')"
      autocomplete="new-password"
    />
    <v-alert
      v-if="formErrors.general && formErrors.general.length"
      type="error"
      class="mt-3"
    >
      {{ formErrors.general[0] }}
    </v-alert>
    <v-btn type="submit" color="primary" block :loading="loading" class="mt-3"
      >Register</v-btn
    >
  </v-form>
</template>

<script>
import { ref, reactive, watch } from 'vue'

export default {
  props: {
    loading: Boolean,
    errors: {
      type: Object,
      default: () => ({}),
    },
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
      general: [],
    })

    const clearError = (field) => {
      formErrors[field] = []
      formErrors.general = []
    }

    const submitForm = () => {
      // Clear previous errors
      Object.keys(formErrors).forEach((key) => (formErrors[key] = []))

      emit('register', {
        username: username.value,
        email: email.value,
        password: password.value,
        password2: password2.value,
      })
    }

    // Watch for errors from parent component
    watch(
      () => props.errors,
      (newErrors) => {
        console.log('[RegisterForm.vue] New errors received:', newErrors)
        Object.keys(formErrors).forEach((key) => {
          if (newErrors[key]) {
            formErrors[key] = Array.isArray(newErrors[key])
              ? newErrors[key]
              : [newErrors[key]]
          } else {
            formErrors[key] = []
          }
        })
      },
      { deep: true }
    )

    return {
      username,
      email,
      password,
      password2,
      formErrors,
      submitForm,
      clearError,
    }
  },
}
</script>
