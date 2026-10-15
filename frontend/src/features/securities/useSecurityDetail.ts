// D7 security detail owner: the single request/state boundary for the five
// characterized resources (detail+chart options, price history, position
// history, transactions, account choices). Trigger sources, invalidation,
// pagination reset and detached snapshots replicate the characterized
// incumbent exactly; children never fetch. No resource commits after the
// owner's scope is disposed or superseded (latest-request generations via
// usePortfolioRequest).
//
// C4: the two history resources negotiate chart contract v2 through the
// shared chart transport (ONE request per history, same triggers) and keep
// the characterized legacy projections for the incumbent charts.
import { computed, ref, watch } from 'vue'

import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import type { PortfolioContext } from '@/types/portfolioContext'
import {
  getAccountChoices,
  getSecurityDetail,
  getSecurityTransactions,
} from '@/services/api'
import { fetchSecurityHistory } from '@/features/charts/chartApi'
import { requireReadyChartContext } from '@/features/charts/useNavChart'
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
  // C4: the two histories negotiate v2 in the same single request that feeds
  // the legacy projection. requireReadyChartContext is total under canRead()
  // (a readable committed context always carries date and currency); a local
  // account filter is sent for position only — the price endpoint has no
  // account parameter.
  const securityHistoryParams = (params: DetailQueryParams, kind: 'price' | 'position') => ({
    context: requireReadyChartContext(params.context),
    securityId: params.id,
    accountId: kind === 'position' ? params.account : null,
    period: params.period,
  })
  const priceQuery = usePortfolioRequest(
    (params: DetailFetcherParams, abort) =>
      fetchSecurityHistory(securityHistoryParams(params, 'price'), 'price', { signal: abort.signal }),
    snapshotDetail,
  )
  const positionQuery = usePortfolioRequest(
    (params: DetailFetcherParams, abort) =>
      fetchSecurityHistory(securityHistoryParams(params, 'position'), 'position', { signal: abort.signal }),
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

  // Account filter: the canonical identity lives below, next to its derived
  // Vuetify display model (identity and display are deliberately separate —
  // see the block after accountOptions).
  const selectedPeriod = ref('1Y')

  const transactionOptions = ref({ page: 1, itemsPerPage: 10 })
  const itemsPerPageOptions = [10, 25, 50, 100] as const

  const security = computed(() => detailQuery.data.value?.security ?? null)
  const securityName = computed(() => security.value?.name ?? '')
  // The characterized legacy projections (price floats / position strings)
  // come from the same negotiated response — identical values, one request.
  const priceHistory = computed(() => priceQuery.data.value?.legacy ?? [])
  const positionHistory = computed(() => positionQuery.data.value?.legacy ?? [])
  // C4: the full negotiated results for the gated security renderers.
  const priceChartResult = computed(() => priceQuery.data.value ?? null)
  const positionChartResult = computed(() => positionQuery.data.value ?? null)
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

  // --- canonical selection identity (request-owning) ------------------------
  // The identity NEVER degrades to a display string: selectedAccountId is
  // derived from it alone, so display fallbacks can never silently broaden
  // the request scope. Only explicit All-accounts/Clear sets the unfiltered
  // identity.
  const selectedAccount = ref<{
    type: 'all' | 'account'
    id?: number | null
    displayName?: string
  }>({ type: 'all', id: null })
  const selectedAccountId = computed(() =>
    selectedAccount.value.type === 'account' && typeof selectedAccount.value.id === 'number'
      ? selectedAccount.value.id
      : null,
  )

  function applyAccountSelection(value: unknown): void {
    if (value == null) {
      // Explicit Clear → the unfiltered scope, on purpose.
      selectedAccount.value = { type: 'all', id: null }
      return
    }
    if (typeof value === 'string') {
      // Display-only echoes never change the identity.
      return
    }
    const candidate = value as { type?: string; id?: unknown }
    if (candidate.type === 'all') {
      selectedAccount.value = { type: 'all', id: null }
      return
    }
    if (candidate.type === 'account' && typeof candidate.id === 'number') {
      // The identity is kept verbatim — matched or not, the request scope
      // stays exactly what the user chose. The display name (when the
      // caller knows it, e.g. a holdings row) rides along so the label
      // fallback stays honest while the choices cannot match.
      selectedAccount.value = {
        type: 'account',
        id: candidate.id,
        displayName: (candidate as { displayName?: string }).displayName,
      }
    }
  }

  // --- Vuetify display model + label (derived, never request-owning) -------
  const findOption = (predicate: (option: { type: string; value?: { type?: string; id?: number | null } }) => boolean) =>
    accountOptions.value.find((option) => option.type === 'option' && predicate(option))
  const ALL_ACCOUNTS_LABEL = 'All accounts'

  // Vuetify's input value derives from the model (PR #54): a model matching
  // no item renders String(model) — '[object Object]'. The model therefore
  // resolves to the MATCHED option's own value whenever the choices contain
  // it, and to a safe label string only as a display fallback. When choices
  // arrive, the model re-derives onto the matched option automatically — no
  // identity write, no extra scope change.
  const selectModel = computed<{ type?: string; id?: number | null } | string>(() => {
    const identity = selectedAccount.value
    if (identity.type === 'all') {
      const matched = findOption((option) => option.value?.type === 'all')
      return matched ? matched.value : ALL_ACCOUNTS_LABEL
    }
    const matched = findOption((option) => option.value?.type === 'account' && option.value?.id === identity.id)
    return matched ? matched.value : identity.displayName ?? 'Unavailable'
  })

  const selectLabel = computed(() => {
    const identity = selectedAccount.value
    if (identity.type === 'all') return ALL_ACCOUNTS_LABEL
    const matched = findOption((option) => option.value?.type === 'account' && option.value?.id === identity.id)
    return matched?.title ?? identity.displayName ?? 'Unavailable'
  })

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
    selectModel,
    selectLabel,
    applyAccountSelection,
    selectedAccountId,
    selectedPeriod,
    transactionOptions,
    itemsPerPageOptions,
    // resources
    security,
    securityName,
    priceHistory,
    positionHistory,
    priceChartResult,
    positionChartResult,
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
