<template>
  <v-card>
    <v-card-title>User Profile</v-card-title>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(value, key) in userInfo" :key="key">
          <template v-slot:title>
            {{ formatLabel(key) }}
          </template>
          <template v-slot:subtitle>
            {{ value || 'Not provided' }}
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
    <v-card-actions>
      <v-btn color="primary" @click="editProfile">Edit Profile</v-btn>
      <v-btn color="primary" @click="showChangePasswordDialog"
        >Change Password</v-btn
      >
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
              autocomplete="current-password"
            />
            <v-text-field
              v-model="passwordForm.new_password1"
              label="New Password"
              type="password"
              required
              :disabled="isLoading"
              :error-messages="passwordErrors.new_password1"
              @input="clearPasswordError('new_password1')"
              autocomplete="new-password"
            />
            <v-text-field
              v-model="passwordForm.new_password2"
              label="Confirm New Password"
              type="password"
              required
              :disabled="isLoading"
              :error-messages="passwordMismatchError"
              @input="clearPasswordError('new_password2')"
              autocomplete="new-password"
            />
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
          <v-spacer />
          <v-btn color="primary" text @click="closeChangePasswordDialog"
            >Close</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Success Dialog -->
    <v-dialog v-model="successDialog" max-width="300">
      <v-card>
        <v-card-title class="text-h5 green--text">Success</v-card-title>
        <v-card-text>{{ successMessage }}</v-card-text>
        <v-card-actions>
          <v-spacer />
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
          <v-spacer />
          <v-btn color="red" text @click="errorDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { changePassword as apiChangePassword } from '@/services/api'
import { useStore } from 'vuex'

export default {
  setup() {
    const componentId = Date.now()
    console.log(`[ProfilePage][${componentId}] Component setup started`)

    const router = useRouter()
    const store = useStore()

    // Get user data from store
    const userInfo = computed(() => {
      const user = store.state.user
      console.log(
        `[ProfilePage][${componentId}] Computing userInfo, user exists:`,
        !!user
      )
      if (!user) return {}
      return {
        username: user.username,
        email: user.email,
        first_name: user.first_name,
        last_name: user.last_name,
      }
    })

    const formatLabel = (key) => {
      return key
        .split('_')
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ')
    }

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
      return passwordForm.new_password1 !== passwordForm.new_password2
        ? ['Passwords do not match']
        : []
    })

    const clearPasswordError = (field) => {
      passwordErrors[field] = []
      errorMessage.value = ''
    }

    const showSuccessMessage = (message) => {
      successMessage.value = message
      successDialog.value = true
    }

    // const showErrorMessage = (message) => {
    //   errorMessage.value = message
    //   errorDialog.value = true
    // }

    const setPasswordErrors = (newErrors) => {
      if (typeof newErrors === 'string') {
        errorMessage.value = newErrors
      } else if (typeof newErrors === 'object') {
        Object.keys(newErrors).forEach((field) => {
          if (field in passwordErrors) {
            passwordErrors[field] = Array.isArray(newErrors[field])
              ? newErrors[field]
              : [newErrors[field]]
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
        const response = await apiChangePassword(passwordForm)
        if (response.success) {
          changePasswordDialog.value = false
          showSuccessMessage(
            response.message || 'Password changed successfully'
          )
          Object.keys(passwordForm).forEach((key) => (passwordForm[key] = ''))
        } else {
          setPasswordErrors(response.error || 'Failed to change password')
        }
      } catch (error) {
        console.error('Error changing password:', error)
        if (error.error === 'Incorrect old password') {
          passwordErrors.old_password = ['Incorrect current password']
        } else {
          setPasswordErrors(error.error || 'An unexpected error occurred')
        }
      } finally {
        isLoading.value = false
      }
    }

    const closeChangePasswordDialog = () => {
      changePasswordDialog.value = false
      Object.keys(passwordForm).forEach((key) => (passwordForm[key] = ''))
      Object.keys(passwordErrors).forEach((key) => (passwordErrors[key] = []))
    }

    const fetchProfile = async () => {
      if (!store.state.user) {
        console.log(
          `[ProfilePage][${componentId}] No user data, fetching profile...`
        )
        await store.dispatch('fetchUserData')
      } else {
        console.log(
          `[ProfilePage][${componentId}] User data exists, skipping fetch`
        )
      }
    }

    onMounted(() => {
      console.log(`[ProfilePage][${componentId}] Component mounted`)
      fetchProfile()
    })

    const editProfile = () => {
      router.push('/profile/edit')
    }

    const showChangePasswordDialog = () => {
      changePasswordDialog.value = true
    }

    return {
      userInfo,
      formatLabel,
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
      editProfile,
      showChangePasswordDialog,
    }
  },
}
</script>
