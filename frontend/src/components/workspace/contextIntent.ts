import type { ContextPatch } from '@/stores/portfolioContext'
import type { PortfolioContext } from '@/types/portfolioContext'
import type { ContextIntent } from './types'

export function toContextPatch(
  intent: ContextIntent,
  committed: Readonly<PortfolioContext>,
  isReady: boolean
): ContextPatch {
  if (!isReady || !committed.effectiveCurrentDate || !committed.currency)
    throw new Error('Portfolio context is not ready.')
  if ('accountSelection' in intent)
    return { accountSelection: intent.accountSelection }
  return {
    effectiveCurrentDate:
      intent.effectiveCurrentDate ?? committed.effectiveCurrentDate,
    currency: intent.currency ?? committed.currency,
    digits: intent.digits ?? committed.digits,
  }
}
