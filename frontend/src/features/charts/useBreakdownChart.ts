// C4 breakdown lifecycle adapter over the shared runner stack — the exact
// useNavChart pattern (C2/C3) for the allocation endpoint: one request feeds
// all three allocation documents, DashboardPage keeps ownership of when
// fetching is triggered, and a context mismatch reconciles at most once per
// episode through the existing reliability store.
import { getCurrentScope, onScopeDispose } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import type { PortfolioContext } from '@/types/portfolioContext'
import type { AllocationResult, BreakdownQuery, ReadyChartContext } from './contracts'
import { ChartContextMismatchError, fetchBreakdownChart } from './chartApi'
import { requireReadyChartContext } from './useNavChart'

/** Detached, frozen query snapshot for the runner to capture. */
export function snapshotBreakdownQuery(query: BreakdownQuery): Readonly<BreakdownQuery> {
  const context = snapshotContext(query.context as PortfolioContext)
  return Object.freeze({ context: Object.freeze({ ...context, effectiveCurrentDate: query.context.effectiveCurrentDate, currency: query.context.currency }) }) as Readonly<BreakdownQuery>
}

/** The dashboard breakdown over the shared request lifecycle. */
export function useBreakdownChart() {
  const context = usePortfolioContextStore()
  const runner = usePortfolioRequest<BreakdownQuery, AllocationResult>(fetchBreakdownChart, snapshotBreakdownQuery)
  let disposed = false
  // One reconciliation per divergence episode (useNavChart semantics): a
  // still-current mismatch may ask the reliability store to reconcile once;
  // the error stays visible until an accepted result or explicit user action.
  let mismatchReconciled = false
  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
    })
  }

  async function run(query: BreakdownQuery): Promise<
    | { status: 'accepted'; data: AllocationResult }
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
    const result = await runner.run({ context: ready })
    if (result.status === 'accepted') {
      mismatchReconciled = false
      return result
    }
    if (result.status === 'failed' && result.error instanceof ChartContextMismatchError) {
      const stillCurrent =
        !disposed &&
        context.canRead &&
        context.committed.revision === ready.revision &&
        runner.error.value === result.error
      if (stillCurrent && !mismatchReconciled) {
        mismatchReconciled = true
        void context.reconcileContext()
      }
    }
    return result
  }

  return { ...runner, run }
}
