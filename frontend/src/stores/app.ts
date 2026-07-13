import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/services/api'
import logger from '@/utils/logger'
// Imported for use inside setAccountSelection only (called at runtime, not at
// module load time, so the lazy dynamic import() in stores/auth.js avoids a
// circular instantiation problem).
import { useAuthStore } from '@/stores/auth'

/**
 * App / UI Pinia store (Composition API style).
 *
 * Owns UI state previously held in the Vuex store: page title, loading,
 * error, account selection, data refresh trigger, effective current date,
 * selected currency, and table/nav-chart settings. Persists
 * accountSelection to localStorage.
 */
export const useAppStore = defineStore('app', () => {
  // ---- State ----
  const pageTitle = ref('')
  const loading = ref(false)
  const error = ref(null)
  const accountSelection = ref(
    JSON.parse(localStorage.getItem('accountSelection')) || {
      type: 'all',
      id: null,
    }
  )
  const dataRefreshTrigger = ref(0)
  const effectiveCurrentDate = ref(null)
  const selectedCurrency = ref(null)
  const tableSettings = ref({
    dateFrom: null,
    dateTo: null,
    timespan: 'all_time',
    page: 1,
    itemsPerPage: 25,
    search: '',
    sortBy: [],
  })
  const itemsPerPageOptions = ref([10, 25, 50, 100])
  const navChartParams = ref({
    frequency: 'Q',
    breakdown: 'none',
    dateRange: 'ytd',
    dateFrom: null,
    dateTo: null,
  })

  // ---- Getters ----
  const currentAccountSelection = computed(() => accountSelection.value)
  const isAllAccountsSelected = computed(
    () => accountSelection.value.type === 'all'
  )
  const selectedAccountType = computed(() => accountSelection.value.type)
  const selectedAccountId = computed(() => accountSelection.value.id)

  // ---- Setters ----
  function setPageTitle(title) {
    pageTitle.value = title
  }

  function setLoading(isLoading) {
    loading.value = isLoading
  }

  function setError(newError) {
    error.value = newError
  }

  function setEffectiveCurrentDate(date) {
    logger.log(
      'AppStore',
      '[DEBUG] setEffectiveCurrentDate - Old value:',
      effectiveCurrentDate.value,
      'New value:',
      date
    )
    effectiveCurrentDate.value = date
  }

  function setSelectedCurrency(currency) {
    selectedCurrency.value = currency
  }

  function setTableSettings(settings) {
    tableSettings.value = { ...tableSettings.value, ...settings }
  }

  function setNavChartParams(params) {
    navChartParams.value = { ...navChartParams.value, ...params }
  }

  /**
   * Sets the account selection. Persists to localStorage and, when a user is
   * logged in, mirrors the selection onto the user object (preserving the
   * previous Vuex mutation behavior).
   */
  function setAccountSelection({ type, id }) {
    accountSelection.value = { type, id }
    localStorage.setItem('accountSelection', JSON.stringify({ type, id }))

    // Mirror onto the current user (if any) to match old Vuex behavior.
    // useAuthStore() is safe to call here because Pinia is already active by
    // the time any component dispatches this setter.
    try {
      const authStore = useAuthStore()
      if (authStore.user) {
        authStore.user.selected_account_type = type
        authStore.user.selected_account_id = id
      }
    } catch (e) {
      // Auth store / Pinia not active yet (e.g. during tests) — ignore.
    }
  }

  // ---- Actions ----
  function triggerDataRefresh() {
    dataRefreshTrigger.value += 1
  }

  async function fetchEffectiveCurrentDate() {
    try {
      logger.log(
        'AppStore',
        '[DEBUG] fetchEffectiveCurrentDate - Fetching from backend...'
      )
      const response = await api.getEffectiveCurrentDate()
      logger.log(
        'AppStore',
        '[DEBUG] fetchEffectiveCurrentDate - Backend response:',
        response
      )
      logger.log(
        'AppStore',
        '[DEBUG] fetchEffectiveCurrentDate - Current store value before set:',
        effectiveCurrentDate.value
      )
      setEffectiveCurrentDate(response.effective_current_date)
      logger.log(
        'AppStore',
        '[DEBUG] fetchEffectiveCurrentDate - New store value after set:',
        effectiveCurrentDate.value
      )
    } catch (error) {
      logger.error('AppStore', 'Failed to fetch effective current date', error)
    }
  }

  function updateEffectiveCurrentDate(date) {
    setEffectiveCurrentDate(date)
  }

  function updateTableSettings(settings) {
    setTableSettings(settings)
  }

  function updateNavChartParams(params) {
    setNavChartParams(params)
  }

  /**
   * Updates the account selection end-to-end: calls the backend to persist
   * the selection, then updates the store and triggers a data refresh.
   */
  async function updateAccountSelection(selection) {
    try {
      await api.updateUserDataForNewAccount({
        type: selection.type,
        id: selection.id,
      })

      setAccountSelection({
        type: selection.type,
        id: selection.id,
      })

      logger.log('AppStore', 'Account selection updated', accountSelection.value)

      triggerDataRefresh()
    } catch (error) {
      logger.error('AppStore', 'Failed to update account selection', error)
      throw error
    }
  }

  return {
    // state
    pageTitle,
    loading,
    error,
    accountSelection,
    dataRefreshTrigger,
    effectiveCurrentDate,
    selectedCurrency,
    tableSettings,
    itemsPerPageOptions,
    navChartParams,
    // getters
    currentAccountSelection,
    isAllAccountsSelected,
    selectedAccountType,
    selectedAccountId,
    // setters
    setPageTitle,
    setLoading,
    setError,
    setEffectiveCurrentDate,
    setSelectedCurrency,
    setTableSettings,
    setNavChartParams,
    setAccountSelection,
    // actions
    triggerDataRefresh,
    fetchEffectiveCurrentDate,
    updateEffectiveCurrentDate,
    updateTableSettings,
    updateNavChartParams,
    updateAccountSelection,
  }
})
