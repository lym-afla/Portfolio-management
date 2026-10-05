import { computed, readonly, shallowRef } from 'vue'
import type { TransactionImportState } from '@/features/imports/types'

// Single discriminated state owner for the transaction import workflow
// (D6). The legacy isIdle/isAnalyzing/isImporting/isMapping/isComplete/
// isError names are computed projections, not stored flags.
export function useImportState() {
  const state = shallowRef<TransactionImportState>({ kind: 'choose-method' })
  const transition = (next: TransactionImportState) => {
    state.value = next
  }
  return {
    state: readonly(state),
    transition,
    isIdle: computed(
      () => ['choose-method', 'configure', 'review'].includes(state.value.kind)
    ),
    isAnalyzing: computed(() => state.value.kind === 'analyzing'),
    isImporting: computed(() => ['running', 'stopping'].includes(state.value.kind)),
    isMapping: computed(() => state.value.kind === 'decision'),
    isComplete: computed(() => state.value.kind === 'complete'),
    isError: computed(() => state.value.kind === 'error'),
  }
}
