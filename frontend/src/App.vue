<template>
  <v-app>
    <v-overlay :model-value="layoutLoading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <template v-if="!layoutLoading">
      <template v-if="isAuthenticated">
        <Navigation @logout="handleLogout" />

        <v-app-bar elevation="1" :height="appBarHeight">
          <div ref="appBarContent" class="app-bar-content" data-testid="app-bar-content">
            <v-container fluid class="py-2">
              <div class="d-flex">
                <h2 v-if="pageTitle" class="text-h4 mb-2">{{ pageTitle }}</h2>
                <SettingsDialog v-if="showSettingsDialog" class="ml-auto" />
              </div>
              <v-divider v-if="pageTitle" class="mb-2" />
              <div v-if="showComponents" class="d-flex align-center flex-wrap mb-2">
                <AccountSelection class="flex-grow-1 app-bar-account-selection" />
                <div class="d-flex align-center">
                  <v-divider vertical class="mx-2" />
                  <SettingsDialog />
                </div>
              </div>
              <v-divider v-if="showComponents" />
            </v-container>
          </div>
        </v-app-bar>

        <v-main>
          <v-container fluid class="pa-4" data-testid="route-content">
            <v-alert v-if="routeChunkRecovery.error.value" type="error" role="alert" class="mb-4" data-testid="route-load-error">
              {{ routeChunkRecovery.error.value }}
              <v-btn @click="routeChunkRecovery.reload">Reload application</v-btn>
            </v-alert>
            <v-alert v-if="!context.isReady" type="warning" role="status" class="mb-4">
              {{ context.transitionError?.message || 'Portfolio context is loading' }}
              <v-btn :loading="context.isTransitioning" :disabled="context.isTransitioning" @click="recoverContext">Recover portfolio context</v-btn>
            </v-alert>
            <div :aria-busy="context.isTransitioning" :inert="context.isTransitioning || !context.isReady">
              <router-view @update-page-title="updatePageTitle" />
            </div>
          </v-container>
        </v-main>
      </template>
      <template v-else>
        <v-main>
          <v-alert v-if="routeChunkRecovery.error.value" type="error" role="alert" class="ma-4" data-testid="route-load-error">
            {{ routeChunkRecovery.error.value }}
            <v-btn @click="routeChunkRecovery.reload">Reload application</v-btn>
          </v-alert>
          <router-view />
        </v-main>
      </template>
    </template>

    <!-- Global Error Snackbar: persists until dismissed (WCAG 2.2.1 timing) -->
    <v-snackbar
      v-model="errorSnackbar"
      :timeout="snackbarTimeout('error')"
      color="error"
      top
      multi-line
    >
      <div v-for="(error, index) in errorMessages" :key="index">
        {{ error }}
      </div>
      <template v-slot:actions>
        <v-btn color="white" text @click="clearErrors"> Close </v-btn>
      </template>
    </v-snackbar>
  </v-app>
</template>

<script setup lang="ts">
import { provide, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { routeChunkRecovery } from './router/chunkRecovery'
import Navigation from './components/Navigation.vue'
import AccountSelection from './components/AccountSelection.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { useRouter, useRoute } from 'vue-router'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAuthStore } from '@/stores/auth'
import logger from '@/utils/logger'
import { snackbarTimeout } from '@/utils/snackbarTimeout'

const context = usePortfolioContextStore()
async function recoverContext() { try { await context.reconcileContext() } catch { /* Error remains visible with retry available. */ } }
const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const user = ref<Record<string, unknown> | null>(null)
const isAuthenticated = computed(() => authStore.isAuthenticated)
const layoutLoading = ref(true)
const pageTitle = ref('')
const appBarHeight = ref(144)
const appBarContent = ref<HTMLElement | null>(null)
let appBarObserver: ResizeObserver | null = null

watch(
  appBarContent,
  (element) => {
    appBarObserver?.disconnect()
    if (!element) return

    const measure = () => {
      // offsetHeight is in layout pixels, including when CSS zoom scales the rectangle.
      const height = element.offsetHeight
      if (height > 0 && height !== appBarHeight.value) appBarHeight.value = height
    }
    appBarObserver = new ResizeObserver(measure)
    appBarObserver.observe(element)
    measure()
  },
  { flush: 'post' },
)
onUnmounted(() => appBarObserver?.disconnect())

const isProfilePage = computed(() => route.path.startsWith('/profile'))
const isDatabasePage = computed(() => route.path.startsWith('/database'))
const isSummaryPage = computed(() => route.path === '/summary')

const showComponents = computed(
  () => !isProfilePage.value && !isDatabasePage.value && !isSummaryPage.value
)
const showSettingsDialog = computed(() => isSummaryPage.value)

const setUser = (userData: Record<string, unknown> | null) => {
  user.value = userData
}

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}

const updatePageTitle = (title: string) => {
  pageTitle.value = title
}

onMounted(() => {
  layoutLoading.value = false
})

const errorSnackbar = ref(false)
const errorMessages = ref<string[]>([])

const showError = (message: string) => {
  clearErrors()
  logger.log('Unknown', 'Showing error:', message)
  errorMessages.value.push(message)
  errorSnackbar.value = true
}

const clearErrors = () => {
  errorMessages.value = []
  errorSnackbar.value = false
}

provide<(message: string) => void>('showError', showError)
provide<() => void>('clearErrors', clearErrors)
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

.app-bar-content {
  width: 100%;
  height: max-content;
}

.app-bar-account-selection {
  min-width: min(100%, 320px);
}

.v-data-table th {
  font-weight: bold !important;
}

.v-data-table th.v-data-table__th {
  vertical-align: bottom;
  padding-bottom: 8px !important;
}

.v-dialog {
  overflow-y: visible;
}
</style>
