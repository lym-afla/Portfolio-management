<template>
  <v-card>
    <v-card-title>User Profile</v-card-title>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(info, index) in userInfo" :key="index">
          <template v-slot:title>
            {{ info.label }}
          </template>
          <template v-slot:subtitle>
            {{ info.value }}
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
    <v-card-actions>
      <v-btn color="primary" @click="editProfile">Edit Profile</v-btn>
      <v-btn color="primary" @click="showChangePasswordDialog">Change Password</v-btn>
    </v-card-actions>

    <!-- Change Password Dialog -->
    <v-dialog v-model="changePasswordDialog" max-width="500px">
      <v-card>
        <v-card-title>Change Password</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="changePassword">
            <v-text-field
              v-model="passwordForm.old_password"
              label="Current Password"
              type="password"
              required
            ></v-text-field>
            <v-text-field
              v-model="passwordForm.new_password1"
              label="New Password"
              type="password"
              required
            ></v-text-field>
            <v-text-field
              v-model="passwordForm.new_password2"
              label="Confirm New Password"
              type="password"
              required
            ></v-text-field>
            <v-btn type="submit" color="primary">Change Password</v-btn>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Success Snackbar -->
    <v-snackbar v-model="snackbar" :timeout="3000" color="success">
      {{ snackbarMessage }}
      <template v-slot:actions>
        <v-btn color="white" text @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </v-card>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      userInfo: [],
      changePasswordDialog: false,
      passwordForm: {
        old_password: '',
        new_password1: '',
        new_password2: '',
      },
      snackbar: false,
      snackbarMessage: '',
    }
  },
  mounted() {
    this.fetchUserDetails()
  },
  methods: {
    async fetchUserDetails() {
      try {
        const response = await axios.get('/users/api/profile/')
        this.userInfo = response.data.user_info
      } catch (error) {
        console.error('Error fetching user details:', error)
      }
    },
    editProfile() {
      this.$router.push('/profile/edit')
    },
    showChangePasswordDialog() {
      this.changePasswordDialog = true
    },
    async changePassword() {
      try {
        await axios.post('/users/api/change-password/', this.passwordForm)
        this.changePasswordDialog = false
        this.showSuccessMessage('Password changed successfully')
        this.passwordForm = { old_password: '', new_password1: '', new_password2: '' }
      } catch (error) {
        console.error('Error changing password:', error)
        this.showErrorMessage('Failed to change password. Please try again.')
      }
    },
    showSuccessMessage(message) {
      this.snackbarMessage = message
      this.snackbar = true
    },
    showErrorMessage(message) {
      this.snackbarMessage = message
      this.snackbar = true
    },
  },
}
</script>