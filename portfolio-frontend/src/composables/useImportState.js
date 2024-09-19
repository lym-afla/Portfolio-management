import { ref, computed } from 'vue'

export function useImportState() {
  const state = ref('idle') // idle, analyzing, importing, mapping, complete, error
  const progress = ref(0)
  const currentMessage = ref('')
  const securityToMap = ref(null)

  const isIdle = computed(() => state.value === 'idle')
  const isAnalyzing = computed(() => state.value === 'analyzing')
  const isImporting = computed(() => state.value === 'importing')
  const isMapping = computed(() => state.value === 'mapping')
  const isComplete = computed(() => state.value === 'complete')
  const isError = computed(() => state.value === 'error')

  const setState = (newState, message = '') => {
    state.value = newState
    currentMessage.value = message
  }

  const setProgress = (value) => {
    progress.value = value
  }

  const setSecurityToMap = (security) => {
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