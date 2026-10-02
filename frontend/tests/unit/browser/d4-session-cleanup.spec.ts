// PR #51 review round — regression for review finding 6:
// the D4 screenshot session must be registered with the harness sessions
// map so cleanupBrowserHarness closes it even when the capture throws.
// (Source assertion, the same pattern used by PositionsPages.spec.js.)
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const src = readFileSync('tests/browser/run-smoke.mjs', 'utf8')

describe('d4 screenshot session cleanup registration', () => {
  it('registers the screenshot session in the harness sessions map', () => {
    // The capture must run through a named session that is added to the
    // sessions map BEFORE the capture (inside its try), so the guaranteed
    // cleanup closes it even when the capture throws.
    const registration = src.match(/sessions\.set\((\w+)[^\n]*\)\n\s*try \{\n\s*await captureD4Screenshots/)
    expect(registration).toBeTruthy()
  })

  it('passes the registered session name to captureD4Screenshots', () => {
    const call = src.match(/await captureD4Screenshots\(\{[^}]*session: (\w+)[^}]*\}\)/s)
    expect(call).toBeTruthy()
    const name = call![1]
    const registration = src.match(new RegExp(`sessions\\.set\\(${name}\\b`))
    expect(registration).toBeTruthy()
  })
})
