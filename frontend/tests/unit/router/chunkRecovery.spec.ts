import { describe, it, expect, vi } from 'vitest'
import { createChunkRecovery } from '@/router/chunkRecovery'

describe('route chunk recovery', () => {
  it('offers one explicit reload without automatically redirecting or reloading', () => {
    const reload = vi.fn()
    const recovery = createChunkRecovery(reload)
    recovery.capture(new Error('Failed to fetch dynamically imported module: /assets/Profile.js'))
    expect(recovery.error.value).toContain('Reload')
    expect(reload).not.toHaveBeenCalled()
    recovery.reload()
    expect(reload).toHaveBeenCalledOnce()
  })
  it('does not misclassify application errors and clears after a successful navigation', () => {
    const recovery = createChunkRecovery(vi.fn())
    recovery.capture(new Error('Permission denied'))
    expect(recovery.error.value).toBeNull()
    recovery.capture(new Error('Importing a module script failed.'))
    expect(recovery.error.value).toBeTruthy()
    recovery.clear()
    expect(recovery.error.value).toBeNull()
  })
})
