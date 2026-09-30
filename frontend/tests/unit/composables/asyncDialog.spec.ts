import { afterEach, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { defineAppDialog } from '@/composables/asyncDialog'
import { routeChunkRecovery } from '@/router/chunkRecovery'

afterEach(() => routeChunkRecovery.clear())

it('reports a failed dialog download through the explicit reload UI state', async () => {
  const dialog = defineAppDialog(() => Promise.reject(new Error('Failed to fetch dynamically imported module: /assets/Import.js')))
  const wrapper = mount(defineComponent({ render: () => h(dialog) }), { global: { config: { errorHandler: () => {} } } })
  await flushPromises()
  expect(routeChunkRecovery.error.value).toContain('Reload')
  wrapper.unmount()
})
