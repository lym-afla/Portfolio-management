import { ref, computed } from 'vue'

export type ImportState = 'idle' | 'analyzing' | 'importing' | 'mapping' | 'complete' | 'error'

export function useImportState() {
  const state = ref<ImportState>('idle')
  const progress = ref(0)
  const currentMessage = ref('')
  const securityToMap = ref<Record<string, unknown> | null>(null)

  const isIdle = computed(() => state.value === 'idle')
  const isAnalyzing = computed(() => state.value === 'analyzing')
  const isImporting = computed(() => state.value === 'importing')
  const isMapping = computed(() => state.value === 'mapping')
  const isComplete = computed(() => state.value === 'complete')
  const isError = computed(() => state.value === 'error')

  const setState = (newState: ImportState, message = '') => {
    state.value = newState
    currentMessage.value = message
  }

  const setProgress = (value: number) => {
    progress.value = value
  }

  const setSecurityToMap = (security: Record<string, unknown>) => {
    securityToMap.value = security
    setState('mapping')
  }

  return {
    state,
    progress,
    currentMessage,
    securityToMap,
    isIdle,
    isAnalyzing,
    isImporting,
    isMapping,
    isComplete,
    isError,
    setState,
    setProgress,
    setSecurityToMap,
  }
}
