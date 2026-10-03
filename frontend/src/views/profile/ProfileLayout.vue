<template>
  <WorkspacePage title="Profile" description="Your account identity, display defaults and broker connections.">
    <div class="profile-layout">
      <nav aria-label="Profile sections" class="profile-layout__nav">
        <v-card border flat rounded="lg" class="profile-nav-card">
          <v-list density="compact" nav>
            <v-list-item
              v-for="item in menuItems"
              :key="item.to"
              :to="item.to"
              :title="item.title"
              :prepend-icon="item.icon"
              :active="isActive(item.to)"
              exact
            />
            <v-divider class="my-2" />
            <v-list-item
              title="Logout"
              prepend-icon="mdi-logout"
              :disabled="isLoading"
              @click="handleLogout"
            />
          </v-list>
        </v-card>
        <v-btn
          color="error"
          variant="outlined"
          block
          class="mt-2 workspace-touch-action"
          prepend-icon="mdi-delete"
          @click="showDeleteConfirmation = true"
        >
          Delete Account
        </v-btn>
      </nav>
      <div class="profile-layout__content">
        <router-view />
      </div>
    </div>

    <!-- Delete Account Confirmation Dialog: the typed DELETE requirement is
         the incumbent constraint and stays exactly as strict. -->
    <v-dialog v-model="showDeleteConfirmation" max-width="400">
      <v-card>
        <v-card-title class="text-h5 text-error">Delete Account</v-card-title>
        <v-card-text>
          Are you sure you want to delete your account? This action cannot be
          undone.
          <v-text-field
            v-model="confirmationText"
            label="Type 'DELETE' to confirm"
            :rules="[(v) => v === 'DELETE' || 'Please type DELETE to confirm']"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="isLoading" @click="cancelDelete">Cancel</v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :disabled="confirmationText !== 'DELETE' || isLoading"
            :loading="isLoading"
            @click="processDeleteAccount"
          >
            Delete Account
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </WorkspacePage>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { deleteUserAccount } from '@/services/api'
import logger from '@/utils/logger'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'

const emit = defineEmits(['update-page-title'])

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const showDeleteConfirmation = ref(false)
const confirmationText = ref('')
const isLoading = ref(false)

const menuItems = [
  { title: 'User details', to: '/profile', icon: 'mdi-account-circle' },
  { title: 'Settings', to: '/profile/settings', icon: 'mdi-cog' },
]

const isActive = (routePath) => {
  return route.path === routePath
}

const handleLogout = async () => {
  isLoading.value = true
  try {
    await authStore.logout()
  } catch (error) {
    logger.error('Unknown', 'Error logging out:', error)
  } finally {
    isLoading.value = false
  }
}

const cancelDelete = () => {
  showDeleteConfirmation.value = false
  confirmationText.value = ''
}

const processDeleteAccount = async () => {
  if (confirmationText.value !== 'DELETE') {
    return
  }
  isLoading.value = true
  try {
    await deleteUserAccount()
    // Clear authentication state
    authStore.clearTokens()
    // Redirect to register page
    router.push('/register')
  } catch (error) {
    logger.error('Unknown', 'Error deleting account:', error)
  } finally {
    isLoading.value = false
    showDeleteConfirmation.value = false
    confirmationText.value = ''
  }
}

onMounted(() => {
  emit('update-page-title', 'User Profile')
})

onBeforeUnmount(() => {
  emit('update-page-title', '') // Clear the page title when component is unmounted
})
</script>

<style scoped>
.profile-layout {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(0, 3fr);
  gap: 24px;
  align-items: start;
}

@media (max-width: 959px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
}
</style>
