// Committed-context valuation date draft (Task 1, real-data corrections).
//
// The header valuation date must commit through the SAME context-change owner
// as every other context control — once per accepted change — whether the
// date arrives from the calendar picker (update:model-value) or from typing
// plus blur/Enter. An invalid or incomplete draft never commits; a rejected
// update restores the committed date; an already-committed draft is a no-op.
import { ref, watch, type Ref } from 'vue'
import { isValid, parseISO, format } from 'date-fns'

/** A draft counts as complete only when it is a real calendar ISO date. */
export function completeIsoDateOrNull(draft: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft)) return null
  const parsed = parseISO(draft)
  if (!isValid(parsed) || format(parsed, 'yyyy-MM-dd') !== draft) return null
  return draft
}

export interface ValuationDateDraftOptions {
  /** The committed effective date from the context store. */
  committed: Ref<string | null>
  canRead: () => boolean
  /** The existing context-change owner (App's requestContextChange). */
  requestContextChange: (intent: { effectiveCurrentDate: string }) => Promise<void>
}

export function useValuationDateDraft(options: ValuationDateDraftOptions) {
  const dateDraft = ref(options.committed.value ?? '')

  watch(
    () => options.committed.value,
    (date) => {
      dateDraft.value = date ?? ''
    }
  )

  /**
   * Commit the current draft once. Returns the committed date, or null when
   * the draft was incomplete/invalid (nothing was sent) or unchanged.
   */
  async function saveDate(): Promise<string | null> {
    const valid = completeIsoDateOrNull(dateDraft.value)
    if (!options.canRead() || valid === null || valid === options.committed.value) {
      return null
    }
    try {
      await options.requestContextChange({ effectiveCurrentDate: valid })
      return valid
    } catch {
      /* The committed context and transition error remain authoritative. */
      return null
    } finally {
      dateDraft.value = options.committed.value ?? ''
    }
  }

  return { dateDraft, saveDate }
}
