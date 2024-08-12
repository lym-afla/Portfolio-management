<template>
  <v-form @submit.prevent="submitForm">
    <v-text-field v-model="username" label="Username" required></v-text-field>
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      required
    ></v-text-field>
    <v-text-field
      v-model="password"
      label="Password"
      type="password"
      required
    ></v-text-field>
    <v-text-field
      v-model="confirmPassword"
      label="Confirm Password"
      type="password"
      required
    ></v-text-field>
    <v-btn type="submit" color="primary" block>Register</v-btn>
  </v-form>
</template>

<script>
import { ref } from 'vue'

export default {
  setup(props, { emit }) {
    const username = ref('')
    const email = ref('')
    const password = ref('')
    const confirmPassword = ref('')

    const submitForm = () => {
      if (password.value !== confirmPassword.value) {
        console.error('Passwords do not match')
        return
      }
      emit('register', {
        username: username.value,
        email: email.value,
        password: password.value,
      })
    }

    return {
      username,
      email,
      password,
      confirmPassword,
      submitForm
    }
  }
}
</script>