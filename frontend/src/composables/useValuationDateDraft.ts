// Committed-context valuation date draft (Task 1, real-data corrections).
//
// The header valuation date must commit through the SAME context-change owner
// as every other context control — once per accepted change — whether the
// date arrives from the calendar picker (change without keyboard interaction)
// or from typing plus blur/Enter. An invalid or incomplete draft never
// commits; a rejected update restores the committed date; an already-committed
// draft is a no-op.
//
// Native date inputs fire `change` for EVERY segment edit, not only on blur
// or picker selection, so a bare @change would commit intermediate typed
// dates (2025-01-08 on the way to 2025-12-31) and each commit's value sync
// resets the input's edit session, swallowing the next keystroke. Keyboard
// interaction therefore arms a guard that defers typed segment edits to the
// blur/Enter commit, while a picker selection — no keydown on the field —
// commits immediately.
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
  const keyboardEditing = ref(false)

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
    keyboardEditing.value = false
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

  /** Arm on keydown: the following change is a typed segment edit. */
  function markKeyboardEditing(): void {
    keyboardEditing.value = true
  }

  /**
   * `change` handler: a keyboard-armed change is a typed intermediate date —
   * blur/Enter will commit it; an unarmed change is a calendar-picker
   * selection and commits immediately.
   */
  function commitDateChange(): Promise<string | null> {
    const fromKeyboard = keyboardEditing.value
    keyboardEditing.value = false
    if (fromKeyboard) return Promise.resolve(null)
    return saveDate()
  }

  return { dateDraft, saveDate, markKeyboardEditing, commitDateChange }
}
