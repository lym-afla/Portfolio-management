import { readonly, ref } from 'vue'

export function createChunkRecovery(reload: () => void) {
  const error = ref<string | null>(null)
  const reportImportFailure = () => {
    error.value = 'This part of the application could not be loaded. Reload to get the latest application, then try again.'
  }
  return {
    error: readonly(error),
    capture(cause: unknown) {
      const message = cause instanceof Error ? cause.message : String(cause)
      if (/Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk .* failed|Failed to load module script/i.test(message)) {
        reportImportFailure()
      }
    },
    reportImportFailure,
    clear() { error.value = null },
    reload,
  }
}

export const routeChunkRecovery = createChunkRecovery(() => window.location.reload())
