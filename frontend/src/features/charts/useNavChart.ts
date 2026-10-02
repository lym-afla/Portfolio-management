// C2 NAV chart lifecycle adapter. Reuses the shared runner stack —
// usePortfolioRequest already invalidates synchronously on revision/readiness
// changes and wraps useLatestRequest's generation guards — so this module
// adds no competing refs, watchers or generation counters. DashboardPage
// keeps ownership of when fetching is triggered.
import { getCurrentScope, onScopeDispose } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import type { PortfolioContext } from '@/types/portfolioContext'
import type { NavQuery, NavResult, ReadyChartContext } from './contracts'
import { ChartContextMismatchError, fetchNavChart } from './chartApi'

/** Refine the committed context to the non-null date/currency a query needs. */
export function requireReadyChartContext(context: PortfolioContext): ReadyChartContext {
  const effectiveCurrentDate = context.effectiveCurrentDate
  const currency = context.currency
  if (effectiveCurrentDate === null || currency === null) {
    throw new Error('Portfolio context is not ready')
  }
  return { ...context, effectiveCurrentDate, currency }
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const key of Object.keys(value as Record<string, unknown>)) {
      deepFreeze((value as Record<string, unknown>)[key])
    }
    Object.freeze(value)
  }
  return value
}

/** Detached, recursively frozen query snapshot for the runner to capture. */
export function snapshotNavQuery(query: NavQuery): Readonly<NavQuery> {
  return deepFreeze(structuredClone(query)) as Readonly<NavQuery>
}

/** The dashboard NAV chart over the shared request lifecycle. */
export function useNavChart() {
  const context = usePortfolioContextStore()
  const runner = usePortfolioRequest<NavQuery, NavResult>(fetchNavChart, snapshotNavQuery)
  let disposed = false
  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
    })
  }

  async function run(query: NavQuery): Promise<
    | { status: 'accepted'; data: NavResult }
    | { status: 'discarded' }
    | { status: 'failed'; error: Error }
  > {
    if (disposed || !context.canRead) return { status: 'discarded' }
    let ready: ReadyChartContext
    try {
      ready = requireReadyChartContext(query.context)
    } catch {
      return { status: 'discarded' }
    }
    const result = await runner.run({ ...query, context: ready })
    if (result.status === 'failed' && result.error instanceof ChartContextMismatchError) {
      // Only a mismatch that still belongs to the current generation, the
      // captured revision, this active scope and a readable store may ask the
      // existing reliability store to reconcile — never an old or logged-out
      // failure, and never a retry loop of our own.
      const stillCurrent =
        !disposed &&
        context.canRead &&
        context.committed.revision === ready.revision &&
        runner.error.value === result.error
      if (stillCurrent) void context.reconcileContext()
    }
    return result
  }

  return { ...runner, run }
}
