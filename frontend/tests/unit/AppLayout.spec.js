import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

// Rendered app-bar/main rectangles are the acceptance gate in tests/browser/layout.mjs.
// These source checks only guard against reintroducing manual offset workarounds.
describe('App layout source hygiene', () => {
  it('App.vue does not use paddingTop / mainPadding compensation', () => {
    const src = readFileSync('src/App.vue', 'utf-8')
    expect(src).not.toContain('mainPadding')
    expect(src).not.toContain('paddingTop')
  })

  it('no router file sets a paddingTop route meta', () => {
    const dir = 'src/router'
    for (const file of readdirSync(dir)) {
      const src = readFileSync(join(dir, file), 'utf-8')
      expect(src, `${dir}/${file} must not set paddingTop meta`).not.toContain(
        'paddingTop'
      )
    }
  })
})
