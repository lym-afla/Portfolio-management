import { describe, it, expect } from 'vitest'
import { snackbarTimeout } from '@/utils/snackbarTimeout'

describe('snackbarTimeout', () => {
  it('persists error snackbars until dismissed (timeout -1)', () => {
    expect(snackbarTimeout('error')).toBe(-1)
  })

  it('auto-hides success/info/warning snackbars after 5000ms', () => {
    expect(snackbarTimeout('success')).toBe(5000)
    expect(snackbarTimeout('info')).toBe(5000)
    expect(snackbarTimeout('warning')).toBe(5000)
  })
})
