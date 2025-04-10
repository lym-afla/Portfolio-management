<template>
  <v-card>
    <v-card-title>Edit Profile</v-card-title>
    <v-card-text>
      <v-form @submit.prevent="saveProfile">
        <v-text-field
          v-for="(value, key) in profileForm"
          :key="key"
          v-model="profileForm[key]"
          :label="formatLabel(key)"
          :disabled="key === 'username'"
          :error-messages="formErrors[key]"
          @input="clearError(key)"
        />
        <v-card-actions>
          <v-btn type="submit" color="primary" :loading="isLoading">Save</v-btn>
          <v-btn @click="cancel" color="secondary">Cancel</v-btn>
        </v-card-actions>
      </v-form>
    </v-card-text>

    <!-- Success Snackbar -->
    <v-snackbar v-model="snackbar" :timeout="3000" :color="snackbarColor">
      {{ snackbarMessage }}
      <template v-slot:actions>
        <v-btn color="white" text @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </v-card>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getUserProfile, editUserProfile } from '@/services/api'
import logger from '@/utils/logger'

export default {
  setup() {
    const router = useRouter()
    const profileForm = reactive({})
    const formErrors = reactive({})
    const isLoading = ref(false)
    const snackbar = ref(false)
    const snackbarMessage = ref('')
    const snackbarColor = ref('success')

    const formatLabel = (key) => {
      return key
        .split('_')
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ')
    }

    const clearError = (field) => {
      if (formErrors[field]) {
        formErrors[field] = []
      }
    }

    const fetchUserDetails = async () => {
      try {
        const response = await getUserProfile()
        Object.keys(response).forEach((key) => {
          profileForm[key] = response[key]
          formErrors[key] = []
        })
      } catch (error) {
        logger.error('Unknown', 'Error fetching user details:', error)
        showErrorMessage('Failed to fetch user details')
      }
    }

    const saveProfile = async () => {
      isLoading.value = true
      try {
        await editUserProfile(profileForm)
        // if (response.success) {
        showSuccessMessage('Profile updated successfully')
        setTimeout(() => {
          router.push('/profile')
        }, 1000)
        // } else {
        //   handleErrors(response.errors)
        // }
      } catch (error) {
        logger.error('Unknown', 'Error saving profile:', error)
        handleErrors(
          error.errors || { general: ['An unexpected error occurred'] }
        )
      } finally {
        isLoading.value = false
      }
    }

    const handleErrors = (errors) => {
      Object.keys(formErrors).forEach((key) => {
        formErrors[key] = errors[key] || []
      })
      if (errors.general) {
        showErrorMessage(errors.general[0])
      } else {
        showErrorMessage(
          'Failed to update profile. Please check the form for errors.'
        )
      }
    }

    const cancel = () => {
      router.push('/profile')
    }

    const showSuccessMessage = (message) => {
      snackbarMessage.value = message
      snackbarColor.value = 'success'
      snackbar.value = true
    }

    const showErrorMessage = (message) => {
      snackbarMessage.value = message
      snackbarColor.value = 'error'
      snackbar.value = true
    }

    onMounted(fetchUserDetails)

    return {
      profileForm,
      formErrors,
      isLoading,
      snackbar,
      snackbarMessage,
      snackbarColor,
      formatLabel,
      clearError,
      saveProfile,
      cancel,
    }
  },
}
</script>
