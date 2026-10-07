// Lazy chart renderer loader (C5a task 1): every legacy Chart.js leaf and
// every modern ECharts leaf loads through this helper. A rejected dynamic
// import must surface as a visible, recoverable renderer error owned by the
// mounting shell — never an empty-success chart, never an automatic retry
// loop. Vue keeps a rejected loader's promise pending forever when a user
// onError neither retries nor fails, and pendingRequest then blocks any
// remount from re-attempting, so the helper owns the single retry path.
import { defineAsyncComponent, ref } from 'vue'
import type { Component, Ref } from 'vue'

export interface LazyChartRenderer {
  /** Async wrapper; render it where the leaf belongs. */
  component: Component
  /** The loader error, set once the chunk download rejects. */
  loadError: Readonly<Ref<Error | null>>
  /** Re-run the download after a visible failure. User-driven only. */
  retry(): void
}

export function lazyChartRenderer(
  load: () => Promise<Component>,
  options: { onLoadError?: (error: Error) => void } = {},
): LazyChartRenderer {
  const loadError = ref<Error | null>(null)
  let pendingRetry: (() => void) | null = null

  const component = defineAsyncComponent({
    loader: load,
    onError(error, retry) {
      const normalized = error instanceof Error ? error : new Error(String(error))
      loadError.value = normalized
      pendingRetry = retry
      options.onLoadError?.(normalized)
    },
  })

  return {
    component,
    loadError: loadError as Readonly<Ref<Error | null>>,
    retry() {
      const retryLoad = pendingRetry
      loadError.value = null
      pendingRetry = null
      retryLoad?.()
    },
  }
}
