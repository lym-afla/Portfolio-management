import type { InjectionKey } from 'vue'

// Workspace pages own their visible heading; the shell releases its duplicate.
export const workspaceHeadingKey: InjectionKey<() => () => void> =
  Symbol('workspace-heading')

import type { PortfolioContext } from '@/types/portfolioContext'
import type { DisplayValue } from '@/types/portfolioTables'

// Presentation-only metric: values cross the API boundary already formatted
// (branded display string or unavailable marker); never a raw number.
export interface MetricDisplay {
  id: string
  label: string
  value: DisplayValue
  unitLabel?: string
  explanation?: string
}

export type ContextIntent =
  | { accountSelection: PortfolioContext['accountSelection'] }
  | Partial<{ effectiveCurrentDate: string; currency: string; digits: number }>
export interface WorkspaceContextView {
  committed: Readonly<PortfolioContext>
  accountLabel: string
  pendingLabel: string | null
  isReady: boolean
  isTransitioning: boolean
  errorMessage: string | null
}
