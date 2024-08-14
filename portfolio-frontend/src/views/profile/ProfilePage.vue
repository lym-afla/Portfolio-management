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
              :disabled="isLoading"
              :error-messages="passwordErrors.old_password"
              @input="clearPasswordError('old_password')"
            ></v-text-field>
            <v-text-field
              v-model="passwordForm.new_password1"
              label="New Password"
              type="password"
              required
              :disabled="isLoading"
              :error-messages="passwordErrors.new_password1"
              @input="clearPasswordError('new_password1')"
            ></v-text-field>
            <v-text-field
              v-model="passwordForm.new_password2"
              label="Confirm New Password"
              type="password"
              required
              :disabled="isLoading"
              :error-messages="passwordMismatchError"
              @input="clearPasswordError('new_password2')"
            ></v-text-field>
            <v-btn 
              type="submit" 
              color="primary" 
              :loading="isLoading"
              :disabled="isLoading"
            >
              Change Password
            </v-btn>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" text @click="closeChangePasswordDialog">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Success Dialog -->
    <v-dialog v-model="successDialog" max-width="300">
      <v-card>
        <v-card-title class="text-h5 green--text">Success</v-card-title>
        <v-card-text>{{ successMessage }}</v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="green" text @click="successDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Error Dialog -->
    <v-dialog v-model="errorDialog" max-width="300">
      <v-card>
        <v-card-title class="text-h5 red--text">Error</v-card-title>
        <v-card-text>{{ errorMessage }}</v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="red" text @click="errorDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import { ref, computed, reactive } from 'vue'
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'

export default {
  setup() {
    const store = useStore()
    const router = useRouter()
    const userInfo = ref([])
    const changePasswordDialog = ref(false)
    const passwordForm = reactive({
      old_password: '',
      new_password1: '',
      new_password2: '',
    })
    const passwordErrors = reactive({
      old_password: [],
      new_password1: [],
      new_password2: [],
    })
    const isLoading = ref(false)
    const successDialog = ref(false)
    const errorDialog = ref(false)
    const successMessage = ref('')
    const errorMessage = ref('')

    const passwordMismatchError = computed(() => {
      return passwordForm.new_password1 !== passwordForm.new_password2 ? ['Passwords do not match'] : []
    })

    const clearPasswordError = (field) => {
      passwordErrors[field] = []
      errorMessage.value = ''
    }

    const showSuccessMessage = (message) => {
      successMessage.value = message
      successDialog.value = true
    }

    const showErrorMessage = (message) => {
      errorMessage.value = message
      errorDialog.value = true
    }

    const setPasswordErrors = (newErrors) => {
      if (typeof newErrors === 'string') {
        errorMessage.value = newErrors
      } else if (typeof newErrors === 'object') {
        Object.keys(newErrors).forEach(field => {
          if (field in passwordErrors) {
            passwordErrors[field] = Array.isArray(newErrors[field]) ? newErrors[field] : [newErrors[field]]
          } else {
            errorMessage.value = newErrors[field]
          }
        })
      }
    }

    const changePassword = async () => {
      if (passwordForm.new_password1 !== passwordForm.new_password2) {
        passwordErrors.new_password2 = ['Passwords do not match']
        return
      }

      isLoading.value = true
      try {
        await store.dispatch('changePassword', passwordForm)
        changePasswordDialog.value = false
        showSuccessMessage('Password changed successfully')
        Object.keys(passwordForm).forEach(key => passwordForm[key] = '')
        Object.keys(passwordErrors).forEach(key => passwordErrors[key] = [])
      } catch (error) {
        console.error('Error changing password:', error)
        if (error.response && error.response.data) {
          setPasswordErrors(error.response.data)
        } else {
          showErrorMessage('Failed to change password. Please try again.')
        }
      } finally {
        isLoading.value = false
      }
    }

    const closeChangePasswordDialog = () => {
      changePasswordDialog.value = false
      Object.keys(passwordForm).forEach(key => passwordForm[key] = '')
      Object.keys(passwordErrors).forEach(key => passwordErrors[key] = [])
    }

    const fetchUserDetails = async () => {
      try {
        console.log('Fetching user profile...')
        const response = await store.dispatch('fetchUserProfile')
        console.log('Received response:', response)
        if (response && response.user_info) {
          userInfo.value = response.user_info
        } else {
          console.error('Unexpected response format:', response)
          showErrorMessage('Unexpected response format')
        }
      } catch (error) {
        console.error('Error fetching user details:', error)
        showErrorMessage(`Failed to fetch user details: ${error.message || 'Unknown error'}`)
      }
    }

    const editProfile = () => {
      router.push('/profile/edit')
    }

    const showChangePasswordDialog = () => {
      changePasswordDialog.value = true
    }

    return {
      userInfo,
      changePasswordDialog,
      passwordForm,
      passwordErrors,
      isLoading,
      successDialog,
      errorDialog,
      successMessage,
      errorMessage,
      passwordMismatchError,
      clearPasswordError,
      changePassword,
      closeChangePasswordDialog,
      fetchUserDetails,
      editProfile,
      showChangePasswordDialog,
    }
  },
  mounted() {
    this.fetchUserDetails()
  },
}
</script>