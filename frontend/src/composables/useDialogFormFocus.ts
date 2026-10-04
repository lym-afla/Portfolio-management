import { nextTick, onUnmounted, watch, getCurrentInstance, type Ref } from 'vue'

// D4's dialog focus contract, extracted for the D5 operational dialogs:
// opening focuses the first ELIGIBLE field — disabled, hidden-type or
// aria-hidden controls are skipped, because focusing them is a silent
// no-op; closing returns focus to the invoking control.
//
// Fields can arrive after the open-time window (slow form_structure
// responses). The fast path polls briefly for the common mount tick; if
// the card is still empty after that, a MutationObserver on this
// instance's own card subtree supplies the focus exactly when a control
// appears — no guessed-longer timeout. The token cancels superseded waits
// (reopen, a later structure load) and unmount cancels the whole pending
// focus; the target is looked up inside THIS instance's own card element
// (id derived from the component uid), so a replacement dialog of the
// same type — which shares DOM patterns but never the id — cannot be
// matched, and a dead instance's late structure response cannot steal
// focus from the replacement.
function firstEligibleControl(card: HTMLElement | null): HTMLElement | null {
  if (!card) return null
  for (const control of card.querySelectorAll<HTMLElement>('input, select, textarea')) {
    if (control instanceof HTMLInputElement && control.type === 'hidden') continue
    if ((control as HTMLInputElement).disabled) continue
    if (control.getAttribute('aria-hidden') === 'true') continue
    if (control.closest('[aria-hidden="true"]')) continue
    return control
  }
  return null
}

export function useDialogFormFocus(dialog: Ref<boolean>, cardIdPrefix: string) {
  let previouslyFocused: HTMLElement | null = null
  let focusToken = 0
  let focusDisposed = false
  let structureObserver: MutationObserver | null = null
  const cardId = `${cardIdPrefix}-${getCurrentInstance()?.uid ?? 'unknown'}-card`

  const cancelStructureObserver = () => {
    structureObserver?.disconnect()
    structureObserver = null
  }

  const focusFirstEligible = async () => {
    if (focusDisposed) return
    const token = ++focusToken
    cancelStructureObserver()
    await nextTick()
    for (let attempt = 0; attempt < 20; attempt++) {
      if (focusDisposed || token !== focusToken || !dialog.value) return
      const control = firstEligibleControl(document.getElementById(cardId))
      if (control) {
        control.focus()
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 10))
    }
    // Slow form structures: watch THIS card's subtree so the focus lands
    // exactly when a control appears, bounded by the dialog's lifetime
    // (close/unmount/reopen cancel the observer), not by a fixed window.
    const card = document.getElementById(cardId)
    if (!card || focusDisposed || token !== focusToken || !dialog.value) return
    structureObserver = new MutationObserver(() => {
      if (focusDisposed || token !== focusToken || !dialog.value) {
        cancelStructureObserver()
        return
      }
      const control = firstEligibleControl(document.getElementById(cardId))
      if (control) {
        cancelStructureObserver()
        control.focus()
      }
    })
    structureObserver.observe(card, { childList: true, subtree: true })
  }

  watch(
    dialog,
    async (open) => {
      if (open) {
        previouslyFocused =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null
        await focusFirstEligible()
      } else {
        cancelStructureObserver()
        if (previouslyFocused?.isConnected) previouslyFocused.focus()
        previouslyFocused = null
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    focusDisposed = true
    focusToken++
    cancelStructureObserver()
  })

  return { cardId }
}
