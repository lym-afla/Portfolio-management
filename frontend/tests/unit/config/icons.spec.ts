import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { globSync } from 'node:fs'
import { iconRegistry, resolveAppIcon, appIcons } from '@/plugins/icons'

describe('SVG icon inventory', () => {
  it('covers every static and dynamic MDI name in application source', () => {
    const names = new Set(globSync('src/**/*.{vue,js,ts}').flatMap(path =>
      [...readFileSync(path, 'utf8').matchAll(/mdi-[a-z0-9]+(?:-[a-z0-9]+)*/g)].map(match => match[0])))
    names.delete('mdi-svg') // Vuetify module name, not an application icon.
    for (const name of names) expect(iconRegistry[name], name).toMatch(/^M/)
  })
  it('rejects unknown names in tests and preserves built-in aliases', () => {
    expect(() => resolveAppIcon('mdi-does-not-exist')).toThrow('Unknown icon')
    expect(appIcons.aliases.close).toBeTruthy()
    expect(appIcons.aliases.dropdown).toBeTruthy()
  })
})
