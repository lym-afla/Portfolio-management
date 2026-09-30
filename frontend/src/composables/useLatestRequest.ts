import { getCurrentScope, onScopeDispose, shallowReadonly, ref, shallowRef } from 'vue'

export type LatestResult<TData> =
  | { status: 'accepted'; data: TData }
  | { status: 'failed'; error: Error }
  | { status: 'discarded' }

/** Cancellation saves work; generations protect state even if transport ignores abort. */
export function useLatestRequest<TParams, TData>(
  fetcher: (params: TParams, options: { signal: AbortSignal }) => Promise<TData>,
  snapshot: (params: TParams) => TParams
) {
  const data = shallowRef<TData | null>(null)
  const error = shallowRef<Error | null>(null)
  const loading = ref(false)
  let generation = 0
  let controller: AbortController | null = null
  let disposed = false

  async function run(params: TParams): Promise<LatestResult<TData>> {
    if (disposed) return { status: 'discarded' }
    const captured = snapshot(params)
    const mine = ++generation
    controller?.abort()
    controller = new AbortController()
    const signal = controller.signal
    loading.value = true
    error.value = null
    try {
      const next = await fetcher(captured, { signal })
      if (mine !== generation || signal.aborted) return { status: 'discarded' }
      data.value = next
      return { status: 'accepted', data: next }
    } catch (cause) {
      if (mine !== generation || signal.aborted) return { status: 'discarded' }
      const failure = cause instanceof Error ? cause : new Error(String(cause))
      error.value = failure
      return { status: 'failed', error: failure }
    } finally {
      if (mine === generation) loading.value = false
    }
  }

  function invalidate(): void {
    generation += 1
    controller?.abort()
    controller = null
    data.value = null
    error.value = null
    loading.value = false
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
      invalidate()
    })
  }

  return { data: shallowReadonly(data), error: shallowReadonly(error), loading: shallowReadonly(loading), run, invalidate }
}
