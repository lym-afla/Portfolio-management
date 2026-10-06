// D7 security detail owner: the single request/state boundary for the five
// characterized resources (detail+chart options, price history, position
// history, transactions, account choices). Trigger sources, invalidation,
// pagination reset and detached snapshots replicate the characterized
// incumbent exactly; children never fetch. No resource commits after the
// owner's scope is disposed or superseded (latest-request generations via
// usePortfolioRequest).
import { computed, ref, watch } from 'vue'

import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import type { PortfolioContext } from '@/types/portfolioContext'
import {
  getAccountChoices,
  getSecurityDetail,
  getSecurityPositionHistory,
  getSecurityPriceHistory,
  getSecurityTransactions,
} from '@/services/api'
import { formatAccountChoices } from '@/utils/accountUtils'
import { getChartOptions } from '@/config/chartConfig'

interface DetailQueryParams {
  context: PortfolioContext
  id: number
  account: number | null
  period: string
  pagination?: { page: number; itemsPerPage: number }
}

const snapshotDetail = (params: DetailQueryParams): DetailQueryParams =>
  Object.freeze({
    ...params,
    context: snapshotContext(params.context),
    ...(params.pagination
      ? { pagination: Object.freeze({ ...params.pagination }) }
      : {}),
  }) as DetailQueryParams

export function useSecurityDetail(options: {
  securityId: () => number
  canRead: () => boolean
  refreshTrigger: () => unknown
  committed: () => PortfolioContext
}) {
  const { securityId, canRead, refreshTrigger, committed } = options

  type DetailFetcherParams = DetailQueryParams
  const detailQuery = usePortfolioRequest(
    async (params: DetailFetcherParams, abort) => {
      const security = await getSecurityDetail(params.id, params.account, abort)
      const chartOptions = await getChartOptions(security.currency)
      return { security, chartOptions }
    },
    snapshotDetail,
  )
  const priceQuery = usePortfolioRequest(
    (params: DetailFetcherParams, abort) =>
      getSecurityPriceHistory(params.id, params.period, abort),
    snapshotDetail,
  )
  const positionQuery = usePortfolioRequest(
    (params: DetailFetcherParams, abort) =>
      getSecurityPositionHistory(params.id, params.period, params.account, abort),
    snapshotDetail,
  )
  const transactionsQuery = usePortfolioRequest(
    (params: DetailFetcherParams, abort) =>
      getSecurityTransactions(params.id, params.pagination as never, params.period, params.account, abort),
    snapshotDetail,
  )
  const accountsQuery = usePortfolioRequest(
    (_params: Parameters<typeof getAccountChoices>[0] extends never ? never : { readonly [field: string]: unknown }, abort) =>
      getAccountChoices(abort),
    snapshotContext as (params: unknown) => unknown,
  )

  // Account filter (raw select model + resolved id, incumbent semantics).
  const selectedAccount = ref<{ type: string; id?: number | null } | null>(null)
  const selectedAccountId = computed(() => {
    if (!selectedAccount.value || selectedAccount.value.type === 'all') return null
    return selectedAccount.value.id as number
  })

  const selectedPeriod = ref('1Y')

  const transactionOptions = ref({ page: 1, itemsPerPage: 10 })
  const itemsPerPageOptions = [10, 25, 50, 100] as const

  const security = computed(() => detailQuery.data.value?.security ?? null)
  const securityName = computed(() => security.value?.name ?? '')
  const priceHistory = computed(() => priceQuery.data.value ?? [])
  const positionHistory = computed(() => positionQuery.data.value ?? [])
  const transactions = computed(
    () =>
      (transactionsQuery.data.value as { transactions?: unknown[] } | null)?.transactions ??
      [],
  )
  const chartOptions = computed(() => detailQuery.data.value?.chartOptions ?? null)
  const chartOptionsLoaded = computed(() => chartOptions.value !== null)
  const loading = computed(() => !canRead() || detailQuery.loading.value)
  const totalTransactions = computed(
    () =>
      (transactionsQuery.data.value as { total_items?: number } | null)?.total_items ??
      0,
  )
  const pageCount = computed(() =>
    Math.ceil(totalTransactions.value / transactionOptions.value.itemsPerPage),
  )
  const loadError = computed(
    () =>
      detailQuery.error.value ||
      priceQuery.error.value ||
      positionQuery.error.value ||
      transactionsQuery.error.value ||
      accountsQuery.error.value,
  )
  const accountOptions = computed(() =>
    formatAccountChoices(accountsQuery.data.value?.options ?? []),
  )

  const detailParams = () => ({
    context: committed(),
    id: securityId(),
    account: selectedAccountId.value,
    period: selectedPeriod.value,
  })

  // Route id/account/period changes reset the transactions page (sync, like
  // the incumbent) while preserving the page size.
  watch(
    [securityId, selectedAccount, selectedPeriod],
    () => {
      transactionOptions.value = { ...transactionOptions.value, page: 1 }
    },
    { flush: 'sync' },
  )
  watch(
    securityId,
    () => {
      detailQuery.invalidate()
      priceQuery.invalidate()
      positionQuery.invalidate()
      transactionsQuery.invalidate()
    },
    { flush: 'sync' },
  )
  watch(
    [canRead, refreshTrigger, securityId, selectedAccountId],
    () => {
      if (canRead()) detailQuery.run(detailParams())
    },
    { immediate: true },
  )
  watch(
    [canRead, refreshTrigger, securityId, selectedAccountId, selectedPeriod],
    () => {
      if (!canRead()) return
      priceQuery.run(detailParams())
      positionQuery.run(detailParams())
    },
    { immediate: true },
  )
  watch(
    [canRead, refreshTrigger, securityId, selectedAccountId, selectedPeriod, transactionOptions],
    () => {
      if (canRead()) {
        transactionsQuery.run({ ...detailParams(), pagination: transactionOptions.value })
      }
    },
    { immediate: true, deep: true },
  )
  watch(
    [canRead, refreshTrigger],
    () => {
      if (canRead()) accountsQuery.run(committed())
    },
    { immediate: true },
  )

  return {
    // selection state
    selectedAccount,
    selectedAccountId,
    selectedPeriod,
    transactionOptions,
    itemsPerPageOptions,
    // resources
    security,
    securityName,
    priceHistory,
    positionHistory,
    transactions,
    chartOptions,
    chartOptionsLoaded,
    accountOptions,
    // status
    loading,
    loadingDetail: detailQuery.loading,
    loadingPriceChart: priceQuery.loading,
    loadingPositionChart: positionQuery.loading,
    loadingTransactions: transactionsQuery.loading,
    totalTransactions,
    pageCount,
    loadError,
  }
}
