import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import type { AccountSelection } from '@/types/portfolioContext'

/** UI preferences; portfolio values delegate to the canonical committed context. */
export const useAppStore = defineStore('app', () => {
  const context = usePortfolioContextStore()
  const pageTitle = ref('')
  const loading = ref(false)
  const error = ref(null)
  const accountSelection = computed(() => context.committed.accountSelection)
  const effectiveCurrentDate = computed(
    () => context.committed.effectiveCurrentDate
  )
  const selectedCurrency = computed(() => context.committed.currency)
  const digits = computed(() => context.committed.digits)
  const dataRefreshTrigger = computed(() => context.dataRefreshTrigger)
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
  const currentAccountSelection = computed(() => accountSelection.value)
  const isAllAccountsSelected = computed(
    () => accountSelection.value.type === 'all'
  )
  const selectedAccountType = computed(() => accountSelection.value.type)
  const selectedAccountId = computed(() => accountSelection.value.id)
  function setPageTitle(title) {
    pageTitle.value = title
  }
  function setLoading(value) {
    loading.value = value
  }
  function setError(value) {
    error.value = value
  }
  function setTableSettings(settings) {
    tableSettings.value = { ...tableSettings.value, ...settings }
  }
  function setNavChartParams(params) {
    navChartParams.value = { ...navChartParams.value, ...params }
  }
  function setEffectiveCurrentDate(date: string) {
    return context.changeContext({ effectiveCurrentDate: date })
  }
  function setSelectedCurrency(currency: string) {
    return context.changeContext({ currency })
  }
  function setAccountSelection(selection: AccountSelection) {
    return context.changeContext({ accountSelection: selection })
  }
  function fetchEffectiveCurrentDate() {
    return context.isReady ? Promise.resolve() : context.reconcileContext()
  }
  return {
    pageTitle,
    loading,
    error,
    accountSelection,
    effectiveCurrentDate,
    selectedCurrency,
    digits,
    dataRefreshTrigger,
    tableSettings,
    itemsPerPageOptions,
    navChartParams,
    currentAccountSelection,
    isAllAccountsSelected,
    selectedAccountType,
    selectedAccountId,
    setPageTitle,
    setLoading,
    setError,
    setTableSettings,
    setNavChartParams,
    setEffectiveCurrentDate,
    setSelectedCurrency,
    setAccountSelection,
    fetchEffectiveCurrentDate,
    triggerDataRefresh: context.triggerDataRefresh,
    updateEffectiveCurrentDate: setEffectiveCurrentDate,
    updateAccountSelection: setAccountSelection,
    updateTableSettings: setTableSettings,
    updateNavChartParams: setNavChartParams,
  }
})
