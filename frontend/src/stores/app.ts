import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import type { AccountSelection } from '@/types/portfolioContext'

interface TableSettings {
  dateFrom: string | null
  dateTo: string | null
  timespan: string
  page: number
  itemsPerPage: number
  search: string
  sortBy: { key: string; order?: boolean | 'asc' | 'desc' }[]
}

interface NavChartParams {
  frequency: string
  breakdown: string
  dateRange: string
  dateFrom: string | null
  dateTo: string | null
}

/** UI preferences; portfolio values delegate to the canonical committed context. */
export const useAppStore = defineStore('app', () => {
  const context = usePortfolioContextStore()
  const pageTitle = ref('')
  const loading = ref(false)
  const error = ref<unknown>(null)
  const accountSelection = computed(() => context.committed.accountSelection)
  const effectiveCurrentDate = computed(
    () => context.committed.effectiveCurrentDate
  )
  const selectedCurrency = computed(() => context.committed.currency)
  const digits = computed(() => context.committed.digits)
  const dataRefreshTrigger = computed(() => context.dataRefreshTrigger)
  const tableSettings = ref<TableSettings>({
    dateFrom: null,
    dateTo: null,
    timespan: 'all_time',
    page: 1,
    itemsPerPage: 25,
    search: '',
    sortBy: [],
  })
  const itemsPerPageOptions = ref([10, 25, 50, 100])
  const navChartParams = ref<NavChartParams>({
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
  function setPageTitle(title: string) {
    pageTitle.value = title
  }
  function setLoading(value: boolean) {
    loading.value = value
  }
  function setError(value: unknown) {
    error.value = value
  }
  function setTableSettings(settings: Partial<TableSettings>) {
    tableSettings.value = { ...tableSettings.value, ...settings }
  }
  watch(accountSelection, (next, previous) => {
    if (
      (next.type !== previous.type || next.id !== previous.id) &&
      tableSettings.value.page !== 1
    ) {
      setTableSettings({ page: 1 })
    }
  })
  function setNavChartParams(params: Partial<NavChartParams>) {
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
