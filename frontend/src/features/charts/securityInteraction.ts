// Controlled interaction model for the security histories (C4). Mirrors the
// NAV viewport model without NAV's multi-series visibility: the zoom window
// is view-only state keyed by server period identity and never changes
// values, queries or observations.
import type { ChartDocument } from './contracts'

export interface SecurityInteraction {
  viewport: { firstPeriodKey: string; lastPeriodKey: string } | null
}

export function defaultSecurityInteraction(): SecurityInteraction {
  return { viewport: null }
}

/** Carry the viewport across documents without inventing identity. */
export function reconcileSecurityInteraction(
  _previous: ChartDocument,
  next: ChartDocument,
  state: SecurityInteraction,
): SecurityInteraction {
  if (!state.viewport) return state
  const keys = new Set(next.periods.map((period) => period.key))
  const survives =
    keys.has(state.viewport.firstPeriodKey) && keys.has(state.viewport.lastPeriodKey)
  return survives ? state : { viewport: null }
}
