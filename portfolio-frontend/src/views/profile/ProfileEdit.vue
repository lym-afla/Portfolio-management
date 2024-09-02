<template>
  <v-card>
    <v-card-title>Edit Profile</v-card-title>
    <v-card-text>
      <v-form @submit.prevent="saveProfile">
        <v-text-field v-model="profileForm.username" label="Username" :disabled="true"></v-text-field>
        <v-text-field v-model="profileForm.first_name" label="First Name"></v-text-field>
        <v-text-field v-model="profileForm.last_name" label="Last Name"></v-text-field>
        <v-text-field v-model="profileForm.email" label="Email"></v-text-field>
        <v-card-actions>
          <v-btn type="submit" color="primary">Save</v-btn>
          <v-btn @click="cancel" color="secondary">Cancel</v-btn>
        </v-card-actions>
      </v-form>
    </v-card-text>

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
import { getUserProfile, editUserProfile } from '@/services/api'

export default {
  data() {
    return {
      profileForm: {
        username: '',
        first_name: '',
        last_name: '',
        email: '',
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
        const response = await getUserProfile()
        const userInfo = response.user_info
        
        userInfo.forEach(item => {
          const key = item.label.toLowerCase().replace(' ', '_')
          if (key in this.profileForm) {
            this.profileForm[key] = item.value
          }
        })
      } catch (error) {
        console.error('Error fetching user details:', error)
      }
    },
    async saveProfile() {
      try {
        const response = await editUserProfile(this.profileForm)
        if (response.success) {
          this.showSuccessMessage('Profile updated successfully')
          setTimeout(() => {
            this.$router.push('/profile')
          }, 1000)
        } else {
          if (response.data.errors) {
            // Handle specific field errors
            const errorMessages = Object.entries(response.data.errors)
              .map(([field, errors]) => `${field}: ${errors.join(', ')}`)
              .join('\n')
            this.showErrorMessage(`Failed to update profile:\n${errorMessages}`)
          } else {
            this.showErrorMessage('Failed to update profile. Please try again.')
          }
        }
      } catch (error) {
        console.error('Error saving profile:', error)
        if (error.response) {
          // The request was made and the server responded with a status code
          // that falls out of the range of 2xx
          if (error.response.status === 400) {
            this.showErrorMessage(`Validation error: ${error.response.data.message || 'Please check your input.'}`)
          } else if (error.response.status === 403) {
            this.showErrorMessage('You do not have permission to perform this action.')
          } else {
            this.showErrorMessage(`Server error: ${error.response.data.message || 'An unexpected error occurred.'}`)
          }
        } else if (error.request) {
          // The request was made but no response was received
          this.showErrorMessage('No response from server. Please check your internet connection.')
        } else {
          // Something happened in setting up the request that triggered an Error
          this.showErrorMessage('An error occurred while saving the profile.')
        }
      }
    },
    cancel() {
      this.$router.push('/profile')
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