<template>
  <v-app>
    <v-overlay :model-value="layoutLoading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <template v-if="!layoutLoading">
      <template v-if="isAuthenticated">
        <Navigation @logout="handleLogout" />
        
        <v-app-bar elevation="1" height="auto">
          <v-container fluid class="py-2">
            <div class="d-flex">
              <h2 v-if="pageTitle" class="text-h4 mb-2">{{ pageTitle }}</h2>
              <SettingsDialog v-if="showSettingsDialog" class="ml-auto" />
            </div>
            <v-divider v-if="pageTitle" class="mb-2"></v-divider> 
            <div v-if="showComponents" class="d-flex align-center mb-2">
              <BrokerSelection class="flex-grow-1" />
              <v-divider vertical class="mx-2" />
              <div>
                <SettingsDialog/>
              </div>
            </div>
            <v-divider v-if="showComponents"></v-divider>
          </v-container>
        </v-app-bar>

        <v-main :style="{ paddingTop: mainPadding }">
          <v-container fluid class="pa-4">
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
      multi-line
    >
      <div v-for="(error, index) in errorMessages" :key="index">
        {{ error }}
      </div>
      <template v-slot:actions>
        <v-btn
          color="white"
          text
          @click="clearErrors"
        >
          Close
        </v-btn>
      </template>
    </v-snackbar>
  </v-app>
</template>

<script>
import { provide, ref, onMounted, computed } from 'vue'
import Navigation from './components/Navigation.vue'
import BrokerSelection from './components/BrokerSelection.vue'
import SettingsDialog from './components/SettingsDialog.vue'
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
    const isAuthenticated = computed(() => store.getters.isAuthenticated)
    const layoutLoading = ref(true)
    const pageTitle = ref('')

    const isProfilePage = computed(() => route.path.startsWith('/profile'))
    const isDatabasePage = computed(() => route.path.startsWith('/database'))
    const isSummaryPage = computed(() => route.path === '/summary')

    const showComponents = computed(() => !isProfilePage.value && !isDatabasePage.value && !isSummaryPage.value)
    // const showBrokerSelection = computed(() => showComponents.value && !isSummaryPage.value)
    const showSettingsDialog = computed(() => isSummaryPage.value)

    const setUser = (userData) => {
      user.value = userData
    }

    // const updateAuthStatus = () => {
    //   if (!isAuthenticated.value && route.meta.requiresAuth) {
    //     router.push('/login')
    //   } else if (isAuthenticated.value && route.path === '/login') {
    //     router.push('/profile')
    //   }
    // }

    const handleLogout = async () => {
      await store.dispatch('logout')
      router.push('/login')
    }

    const updatePageTitle = (title) => {
      pageTitle.value = title
    }

    const mainPadding = computed(() => {
      return route.meta.paddingTop || '140px' // Default padding
    })

    const init = async () => {
      layoutLoading.value = true
      await store.dispatch('initializeApp')
      layoutLoading.value = false
    }

    onMounted(() => {
      init()
    })

    const errorSnackbar = ref(false)
    const errorMessages = ref([])

    const showError = (message) => {
      clearErrors()
      console.log('Showing error:', message)
      errorMessages.value.push(message)
      errorSnackbar.value = true
    }

    const clearErrors = () => {
      errorMessages.value = []
      errorSnackbar.value = false
    }

    provide('showError', showError)
    provide('clearErrors', clearErrors)

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
      errorMessages,
      clearErrors,
      mainPadding,
      showComponents,
      showSettingsDialog,
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
