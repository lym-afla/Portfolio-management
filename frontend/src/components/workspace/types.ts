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

// D4 shared toolbar/action/confirmation presentation contracts. Components
// carrying these types emit intent only; parents own data, requests and
// selection identity.
export interface WorkspaceAction {
  id: string
  label: string
  icon?: string
  disabled?: boolean
  loading?: boolean
}

export interface TableQueryView {
  search: string
  page: number
  itemsPerPage: number
}

export interface ConfirmationSubject {
  title: string
  confirmLabel: string
  details: readonly { label: string; value: string }[]
}

