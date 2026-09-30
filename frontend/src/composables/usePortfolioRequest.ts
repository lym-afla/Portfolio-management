import { watch } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useLatestRequest } from './useLatestRequest'

/** Suspend and discard reads before a context mutation reaches its first await. */
export function usePortfolioRequest<TParams, TData>(
  fetcher: (params: TParams, options: { signal: AbortSignal }) => Promise<TData>,
  snapshot: (params: TParams) => TParams
) {
  const context = usePortfolioContextStore()
  const query = useLatestRequest(fetcher, snapshot)
  watch(
    [() => context.committed.revision, () => context.canRead],
    () => query.invalidate(),
    { flush: 'sync' }
  )
  return {
    ...query,
    run: (params: TParams) => context.canRead
      ? query.run(params)
      : Promise.resolve({ status: 'discarded' as const }),
  }
}
