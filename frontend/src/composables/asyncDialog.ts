import { defineAsyncComponent, type Component } from 'vue'
import { routeChunkRecovery } from '@/router/chunkRecovery'

export function defineAppDialog(loader: () => Promise<Component | { default: Component }>) {
  return defineAsyncComponent({
    async loader() {
      try { return await loader() }
      catch {
        // The app shell owns explicit reload recovery; avoid an unhandled
        // component error in addition to that visible feedback.
        routeChunkRecovery.reportImportFailure()
        return { render: () => null }
      }
    },
  })
}
