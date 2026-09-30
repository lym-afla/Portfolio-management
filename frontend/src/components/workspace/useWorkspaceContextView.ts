import { computed } from 'vue'
import type { PortfolioContext } from '@/types/portfolioContext'
import type { WorkspaceContextView } from './types'
interface ContextSource {
  committed: Readonly<PortfolioContext>
  isReady: boolean
  isTransitioning: boolean
  transitionError: Error | null
}
export function useWorkspaceContextView(
  store: ContextSource,
  accountLabel: () => string,
  pendingLabel: () => string | null
) {
  return computed<WorkspaceContextView>(() => ({
    committed: store.committed,
    accountLabel: accountLabel(),
    pendingLabel: store.isTransitioning ? pendingLabel() : null,
    isReady: store.isReady,
    isTransitioning: store.isTransitioning,
    errorMessage: store.transitionError?.message ?? null,
  }))
}
