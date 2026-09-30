import { describe, it, expect } from 'vitest'
import { effectScope, ref } from 'vue'
import { useFirstOpen } from '@/composables/useFirstOpen'

describe('on-demand dialog lifetime', () => {
  it('mounts on first open, then retains the session after closing', () => {
    const scope = effectScope()
    const open = ref(false)
    const mounted = scope.run(() => useFirstOpen(open))!
    expect(mounted.value).toBe(false)
    open.value = true
    expect(mounted.value).toBe(true)
    open.value = false
    expect(mounted.value).toBe(true)
    scope.stop()
  })
  it('supports an initially open dialog', () => {
    const scope = effectScope()
    expect(scope.run(() => useFirstOpen(ref(true)))!.value).toBe(true)
    scope.stop()
  })
})
