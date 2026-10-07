// Controlled interaction model for the security histories (C4). Mirrors the
// NAV viewport model without NAV's multi-series visibility: the zoom window
// is view-only state keyed by server period identity (or the presentation-
// only carry-forward endpoint) and never changes values, queries or
// observations. Key membership always checks the FULL plotted axis via
// securityAxisKeys, so viewport state and the rendered axis can never
// disagree about what exists.
import type { ChartDocument } from './contracts'
import { securityAxisKeys } from './buildSecurityOption'

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
  const keys = new Set(securityAxisKeys(next))
  const survives =
    keys.has(state.viewport.firstPeriodKey) && keys.has(state.viewport.lastPeriodKey)
  return survives ? state : { viewport: null }
}
