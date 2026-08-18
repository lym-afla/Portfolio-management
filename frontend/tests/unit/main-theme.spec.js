// tests/unit/main-theme.spec.js
import { describe, it, expect } from 'vitest'
import { createAppTheme } from '@/theme'

describe('createAppTheme', () => {
  it('exposes required light-theme tokens', () => {
    const theme = createAppTheme()
    expect(Object.keys(theme.themes.light.colors)).toEqual(
      expect.arrayContaining([
        'primary', 'secondary', 'background', 'surface', 'success', 'error',
      ])
    )
    expect(theme.defaultTheme).toBe('light')
  })
})
