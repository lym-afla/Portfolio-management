// D4 Task 2 — per-table, per-user presentation preferences for the two
// position tables. Presentation state only: query/sort/search settings are
// NOT stored here, and the saved choice never changes on resize.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePositionsTableView } from '@/composables/usePositionsTableView'
import { useAuthStore } from '@/stores/auth'
import { buildPositionView } from '@/config/positionsTableViews'

const storageKey = (userId: number | string, tableId: string) =>
  `positionsTableView.v1.u${userId}.${tableId}`

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('usePositionsTableView persistence', () => {
  it('defaults new/unconfigured views to Overview', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const view = usePositionsTableView('open-positions')
    expect(view.preset.value).toBe('overview')
    expect(buildPositionView('open-positions', view.preset.value, view.visibleKeys.value, 'USD').leafKeys)
      .toEqual(['name', 'currency', 'entry_value', 'current_value', 'share_of_portfolio',
        'total_return_amount', 'total_return_percentage', 'irr'])
  })

  it('keeps open and closed table preferences independent', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const open = usePositionsTableView('open-positions')
    const closed = usePositionsTableView('closed-positions')
    open.setPreset('full-ledger')
    expect(open.preset.value).toBe('full-ledger')
    expect(closed.preset.value).toBe('overview')
    expect(localStorage.getItem(storageKey(7, 'open-positions'))).toBeTruthy()
    expect(localStorage.getItem(storageKey(7, 'closed-positions'))).toBeNull()
  })

  it('never shares preferences across users', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const alice = usePositionsTableView('open-positions')
    alice.setPreset('full-ledger')
    auth.user = { id: 8, username: 'bob' }
    const bob = usePositionsTableView('open-positions')
    expect(bob.preset.value).toBe('overview')
    expect(bob.visibleKeys.value).not.toContain('entry_price')
  })

  it('restores a saved Full ledger on a fresh instance (navigation/refresh)', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    usePositionsTableView('open-positions').setPreset('full-ledger')
    const restored = usePositionsTableView('open-positions')
    expect(restored.preset.value).toBe('full-ledger')
    expect(restored.visibleKeys.value).toHaveLength(20)
  })

  it('falls back to Overview for corrupt, malformed or wrong-version storage', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    localStorage.setItem(storageKey(7, 'open-positions'), '{not json')
    expect(usePositionsTableView('open-positions').preset.value).toBe('overview')
    localStorage.setItem(storageKey(7, 'open-positions'), JSON.stringify({ version: 99, preset: 'comparison' }))
    expect(usePositionsTableView('open-positions').preset.value).toBe('overview')
    localStorage.setItem(storageKey(7, 'open-positions'), JSON.stringify({ version: 1, preset: 'nonsense' }))
    expect(usePositionsTableView('open-positions').preset.value).toBe('overview')
    localStorage.setItem(storageKey(7, 'open-positions'), JSON.stringify({ version: 1, preset: 'custom', visibleKeys: 'nope' }))
    expect(usePositionsTableView('open-positions').preset.value).toBe('overview')
  })

  it('filters invalid keys and forces the security identity on custom views', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    localStorage.setItem(storageKey(7, 'open-positions'), JSON.stringify({
      version: 1, preset: 'custom', visibleKeys: ['bogus', 'irr', 'entry_price', 'ghost'],
    }))
    const view = usePositionsTableView('open-positions')
    expect(view.preset.value).toBe('custom')
    // Canonical order, unknown keys dropped, name forced visible.
    expect(view.visibleKeys.value).toEqual(['name', 'entry_price', 'irr'])
  })

  it('locks the Security leaf against hiding', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const view = usePositionsTableView('open-positions')
    view.setPreset('full-ledger')
    view.toggleColumn('name')
    expect(view.visibleKeys.value).toContain('name')
    // Hiding every other leaf still leaves the identity in place.
    for (const key of [...view.visibleKeys.value]) {
      if (key !== 'name') view.toggleColumn(key)
    }
    expect(view.visibleKeys.value).toEqual(['name'])
    expect(view.preset.value).toBe('custom')
  })

  it('toggling a leaf yields Custom without erasing the prior selection', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const view = usePositionsTableView('open-positions')
    view.setPreset('comparison')
    view.toggleColumn('irr')
    expect(view.preset.value).toBe('custom')
    // All comparison keys survive plus the newly added IRR.
    expect(view.visibleKeys.value).toEqual([
      'name', 'currency', 'investment_date', 'entry_price', 'entry_value',
      'current_price', 'current_value', 'share_of_portfolio', 'irr',
    ])
  })

  it('resetView returns to Overview', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const view = usePositionsTableView('closed-positions')
    view.setPreset('full-ledger')
    view.resetView()
    expect(view.preset.value).toBe('overview')
  })

  it('never mutates the saved choice on window resize', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const view = usePositionsTableView('open-positions')
    view.setPreset('full-ledger')
    const saved = localStorage.getItem(storageKey(7, 'open-positions'))
    window.dispatchEvent(new Event('resize'))
    window.dispatchEvent(new Event('resize'))
    expect(view.preset.value).toBe('full-ledger')
    expect(localStorage.getItem(storageKey(7, 'open-positions'))).toBe(saved)
  })

  it('does not persist or read shared state while the user is unknown', () => {
    const auth = useAuthStore()
    auth.user = null
    const view = usePositionsTableView('open-positions')
    view.setPreset('full-ledger')
    expect(localStorage.length).toBe(0)
    // A later identity change loads that user's stored state.
    auth.user = { id: 9, username: 'carol' }
    expect(usePositionsTableView('open-positions').preset.value).toBe('overview')
  })

  it('tolerates unavailable storage without crashing', () => {
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'alice' }
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    const view = usePositionsTableView('open-positions')
    expect(view.preset.value).toBe('overview')
    expect(() => view.setPreset('full-ledger')).not.toThrow()
    expect(view.preset.value).toBe('full-ledger')
    spy.mockRestore()
    setSpy.mockRestore()
  })
})
