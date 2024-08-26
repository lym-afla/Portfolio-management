<template>
  <v-app>
    <v-overlay :model-value="layoutLoading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <template v-if="!layoutLoading">
      <template v-if="isAuthenticated">
        <Navigation @logout="handleLogout" />
        <v-main>
          <v-container fluid class="pa-4">
            <h2 v-if="pageTitle" class="text-h4 mb-2">{{ pageTitle }}</h2>
            <v-divider v-if="pageTitle" class="mb-2"></v-divider>
            <div v-if="!isProfilePage && !isDatabasePage" class="d-flex align-center mb-4">
              <BrokerSelection class="flex-grow-1" />
              <v-divider vertical class="mx-2" />
              <SettingsDialog />
            </div>
            <v-divider v-if="!isProfilePage && !isDatabasePage" class="mb-4"></v-divider>
            <router-view @update-page-title="updatePageTitle"></router-view>
          </v-container>
        </v-main>
      </template>
      <template v-else>
        <v-main>
          <router-view></router-view>
        </v-main>
      </template>
    </template>

    <!-- Global Error Snackbar -->
    <v-snackbar
      v-model="errorSnackbar"
      :timeout="5000"
      color="error"
      top
    >
      {{ errorMessage }}
      <template v-slot:actions>
        <v-btn
          color="white"
          text
          @click="errorSnackbar = false"
        >
          Close
        </v-btn>
      </template>
    </v-snackbar>
  </v-app>
</template>

<script>
import { provide, ref, onMounted, watch, computed } from 'vue'
import Navigation from './components/Navigation.vue'
import BrokerSelection from './components/BrokerSelection.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { checkAuth } from './utils/auth'
import { useRouter, useRoute } from 'vue-router'
import { useStore } from 'vuex'

export default {
  name: 'App',
  components: {
    Navigation,
    BrokerSelection,
    SettingsDialog,
  },
  setup() {
    const store = useStore()
    const router = useRouter()
    const route = useRoute()
    const user = ref(null)
    const isAuthenticated = ref(false)
    const layoutLoading = ref(true)
    const pageTitle = ref('')

    const isProfilePage = computed(() => {
      return route.path.startsWith('/profile')
    })

    const isDatabasePage = computed(() => {
      return route.path.startsWith('/database')
    })

    const setUser = (userData) => {
      user.value = userData
    }

    const updateAuthStatus = async () => {
      layoutLoading.value = true
      isAuthenticated.value = await checkAuth()
      if (!isAuthenticated.value && route.meta.requiresAuth) {
        router.push('/login')
      }
      layoutLoading.value = false
    }

    const handleLogout = () => {
      setUser(null)
      isAuthenticated.value = false
      router.push('/login')
    }

    const updatePageTitle = (title) => {
      pageTitle.value = title
    }

    onMounted(() => {
      updateAuthStatus()
      console.log('Is authenticated:', store.getters.isAuthenticated)
    })

    watch(() => route.fullPath, updateAuthStatus)

    provide('user', user)
    provide('setUser', setUser)
    provide('isAuthenticated', isAuthenticated)

    const errorSnackbar = ref(false)
    const errorMessage = ref('')

    const showError = (message) => {
      errorMessage.value = message
      errorSnackbar.value = true
    }

    provide('showError', showError)

    return {
      user,
      setUser,
      router,
      isAuthenticated,
      layoutLoading,
      pageTitle,
      handleLogout,
      updatePageTitle,
      isProfilePage,
      isDatabasePage,
      errorSnackbar,
      errorMessage,
    }
  },
}
</script>

<style>
html {
  overflow-y: scroll;
}

body {
  overflow-x: hidden;
}

.v-application {
  overflow-x: hidden;
}

.v-data-table th {
  font-weight: bold !important;
}

.v-data-table th.v-data-table__th {
  vertical-align: bottom !important;
  padding-bottom: 8px !important;
  white-space: normal;
  hyphens: auto;
}

.v-data-table td {
  white-space: normal;
  hyphens: auto;
}

.v-dialog {
  overflow-y: visible;
}
</style>
