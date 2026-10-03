import { nextTick, onUnmounted, watch, getCurrentInstance, type Ref } from 'vue'

// D4's dialog focus contract, extracted for the D5 operational dialogs:
// opening focuses the first field (fields can arrive after the open window —
// slow form structures — so the lookup polls briefly); closing returns focus
// to the invoking control. The token cancels superseded polls (reopen, a
// later structure load) and unmount cancels the whole pending focus; the
// target is looked up inside THIS instance's own card element so a
// replacement dialog of the same type can never receive the focus.
export function useDialogFormFocus(dialog: Ref<boolean>, cardIdPrefix: string) {
  let previouslyFocused: HTMLElement | null = null
  let focusToken = 0
  let focusDisposed = false
  const cardId = `${cardIdPrefix}-${getCurrentInstance()?.uid ?? 'unknown'}-card`

  const focusFirstField = async () => {
    if (focusDisposed) return
    const token = ++focusToken
    await nextTick()
    for (let attempt = 0; attempt < 20; attempt++) {
      if (focusDisposed || token !== focusToken || !dialog.value) return
      const first = document
        .getElementById(cardId)
        ?.querySelector('input, select, textarea:not([aria-hidden])')
      if (first instanceof HTMLElement) {
        first.focus()
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 10))
    }
  }

  watch(
    dialog,
    async (open) => {
      if (open) {
        previouslyFocused =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null
        await focusFirstField()
      } else {
        if (previouslyFocused?.isConnected) previouslyFocused.focus()
        previouslyFocused = null
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    focusDisposed = true
    focusToken++
  })

  return { cardId }
}
