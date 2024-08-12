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
export default {
  data() {
    return {
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    }
  },
  methods: {
    submitForm() {
      if (this.password !== this.confirmPassword) {
        console.error('Passwords do not match')
        return
      }
      this.$emit('register', {
        username: this.username,
        email: this.email,
        password: this.password,
      })
    },
  },
}
</script>
