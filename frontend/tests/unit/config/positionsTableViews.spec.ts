// D4 Task 1 — pure preset/view derivation over the original header keys.
// The original 20 open / 16 closed leaf keys are inventoried here first so
// the restructuring cannot silently drop or rename a financial field.
import { describe, expect, it } from 'vitest'
import {
  buildPositionView,
  positionPresets,
  positionTableLeaves,
  POSITION_GROUP_ORDER,
  type PositionPresetId,
  type PositionTableId,
} from '@/config/positionsTableViews'
import {
  closedPositionsHeaders,
  flattenHeaders,
  openPositionsHeaders,
} from '@/config/positionsHeaders'

const openKeys = flattenHeaders(openPositionsHeaders).map((h) => String(h.key))
const closedKeys = flattenHeaders(closedPositionsHeaders).map((h) => String(h.key))

describe('original key inventory (20 open / 16 closed, unchanged)', () => {
  it('keeps the exact original open leaf key set', () => {
    expect(openKeys).toEqual([
      'type', 'name', 'currency', 'current_position',
      'investment_date', 'entry_price', 'entry_value',
      'current_price', 'current_value', 'share_of_portfolio',
      'price_change_percentage', 'realized_gl', 'unrealized_gl',
      'capital_distribution', 'capital_distribution_percentage',
      'commission', 'commission_percentage',
      'total_return_amount', 'total_return_percentage', 'irr',
    ])
    expect(openKeys).toHaveLength(20)
  })

  it('keeps the exact original closed leaf key set', () => {
    expect(closedKeys).toEqual([
      'type', 'name', 'currency',
      'investment_date', 'entry_value',
      'exit_date', 'exit_value',
      'realized_gl', 'price_change_percentage',
      'capital_distribution', 'capital_distribution_percentage',
      'commission', 'commission_percentage',
      'total_return_amount', 'total_return_percentage', 'irr',
    ])
    expect(closedKeys).toHaveLength(16)
  })

  it('derives the same leaf key order from the view metadata registry', () => {
    expect(positionTableLeaves('open-positions').map((leaf) => leaf.key)).toEqual(openKeys)
    expect(positionTableLeaves('closed-positions').map((leaf) => leaf.key)).toEqual(closedKeys)
  })
})

describe('positionPresets', () => {
  it('offers the exact Overview key lists', () => {
    expect(positionPresets('open-positions').find((p) => p.id === 'overview')?.keys).toEqual([
      'name', 'currency', 'entry_value', 'current_value', 'share_of_portfolio',
      'total_return_amount', 'total_return_percentage', 'irr',
    ])
    expect(positionPresets('closed-positions').find((p) => p.id === 'overview')?.keys).toEqual([
      'name', 'currency', 'entry_value', 'exit_value',
      'total_return_amount', 'total_return_percentage', 'irr',
    ])
  })

  it('offers the exact Comparison key lists', () => {
    expect(positionPresets('open-positions').find((p) => p.id === 'comparison')?.keys).toEqual([
      'name', 'currency', 'investment_date', 'entry_price', 'entry_value',
      'current_price', 'current_value', 'share_of_portfolio',
    ])
    expect(positionPresets('closed-positions').find((p) => p.id === 'comparison')?.keys).toEqual([
      'name', 'currency', 'investment_date', 'entry_value', 'exit_date', 'exit_value',
    ])
  })

  it('full ledger covers every original key on both tables', () => {
    for (const tableId of ['open-positions', 'closed-positions'] as PositionTableId[]) {
      const full = buildPositionView(tableId, 'full-ledger', null, 'USD')
      expect(full.leafKeys).toEqual(tableId === 'open-positions' ? openKeys : closedKeys)
    }
  })

  it('every preset label is visible and preset ids are stable', () => {
    for (const tableId of ['open-positions', 'closed-positions'] as PositionTableId[]) {
      const presets = positionPresets(tableId)
      expect(presets.map((p) => p.id)).toEqual(['overview', 'comparison', 'full-ledger'])
      for (const preset of presets) expect(preset.label.trim().length).toBeGreaterThan(0)
    }
  })
})

describe('buildPositionView grouping', () => {
  it('splits the open full ledger into Identity 4 / Entry 3 / Current 3 / Performance 10', () => {
    const view = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const byGroup = view.groups.map((group) => [group.id, group.keys.length])
    expect(byGroup).toEqual([
      ['identity', 4], ['entry', 3], ['current', 3], ['performance', 10],
    ])
  })

  it('splits the closed full ledger into Identity 3 / Entry 2 / Exit 2 / Performance 9', () => {
    const view = buildPositionView('closed-positions', 'full-ledger', null, 'USD')
    const byGroup = view.groups.map((group) => [group.id, group.keys.length])
    expect(byGroup).toEqual([
      ['identity', 3], ['entry', 2], ['exit', 2], ['performance', 9],
    ])
  })

  it('closed table never invents entry/exit price leaves', () => {
    const view = buildPositionView('closed-positions', 'full-ledger', null, 'USD')
    for (const forbidden of ['entry_price', 'current_price', 'exit_price']) {
      expect(view.leafKeys).not.toContain(forbidden)
    }
  })

  it('uses at most two structural header rows; Overview is one flat row', () => {
    const presets: PositionPresetId[] = ['overview', 'comparison', 'full-ledger', 'custom']
    for (const tableId of ['open-positions', 'closed-positions'] as PositionTableId[]) {
      for (const preset of presets) {
        const view = buildPositionView(tableId, preset, preset === 'custom' ? ['name', 'irr'] : null, 'USD')
        expect(view.headerRows.length).toBeLessThanOrEqual(2)
      }
      expect(buildPositionView(tableId, 'overview', null, 'USD').headerRows).toHaveLength(1)
    }
  })

  it('drops empty groups and recomputes first-leaf boundaries for custom views', () => {
    const view = buildPositionView('open-positions', 'custom',
      ['irr', 'entry_price', 'name', 'total_return_percentage'], 'USD')
    // Canonical order inside each group is preserved regardless of selection order.
    expect(view.leafKeys).toEqual(['name', 'entry_price', 'total_return_percentage', 'irr'])
    expect(view.groups.map((group) => group.id)).toEqual(['identity', 'entry', 'performance'])
    const firstKeys = view.leaves.filter((leaf) => leaf.isFirstOfGroup).map((leaf) => leaf.key)
    expect(firstKeys).toEqual(['name', 'entry_price', 'total_return_percentage'])
  })

  it('keeps the security identity visible even when every key is hidden', () => {
    expect(buildPositionView('open-positions', 'custom', [], 'USD').leafKeys).toEqual(['name'])
    expect(buildPositionView('closed-positions', 'custom', [], 'USD').leafKeys).toEqual(['name'])
  })

  it('ignores unknown keys without failing', () => {
    const view = buildPositionView('open-positions', 'custom', ['bogus', 'name', 'nope'], 'USD')
    expect(view.leafKeys).toEqual(['name'])
  })

  it('qualifies repeated Date/Price/Value/Amount/% labels with distinct full titles', () => {
    const open = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const closed = buildPositionView('closed-positions', 'full-ledger', null, 'USD')
    const fullTitle = (view, key) => view.leaves.find((leaf) => leaf.key === key)?.fullTitle
    expect(fullTitle(open, 'investment_date')).toBe('Entry date')
    expect(fullTitle(closed, 'investment_date')).toBe('Entry date')
    expect(fullTitle(closed, 'exit_date')).toBe('Exit date')
    expect(fullTitle(open, 'entry_price')).toBe('Entry price')
    expect(fullTitle(open, 'current_price')).toBe('Current price')
    expect(fullTitle(open, 'entry_value')).toBe('Entry value')
    expect(fullTitle(open, 'current_value')).toBe('Current value')
    expect(fullTitle(closed, 'exit_value')).toBe('Exit value')
    // Flattened closed Amount/% leaves carry qualified Performance titles.
    expect(fullTitle(closed, 'realized_gl')).toBe('Realized G/L amount')
    expect(fullTitle(closed, 'price_change_percentage')).toBe('Realized G/L %')
    expect(fullTitle(closed, 'capital_distribution')).toBe('Capital distribution amount')
    expect(fullTitle(closed, 'capital_distribution_percentage')).toBe('Capital distribution %')
    expect(fullTitle(closed, 'commission')).toBe('Commission amount')
    expect(fullTitle(closed, 'commission_percentage')).toBe('Commission %')
    expect(fullTitle(closed, 'total_return_amount')).toBe('Total return amount')
    expect(fullTitle(closed, 'total_return_percentage')).toBe('Total return %')
    // Every full title on a table is unique.
    for (const view of [open, closed]) {
      expect(new Set(view.leaves.map((leaf) => leaf.fullTitle)).size).toBe(view.leaves.length)
    }
  })

  it('marks the security name as the pinned identity leaf and only pins identity leaves', () => {
    const view = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const pinned = view.leaves.filter((leaf) => leaf.pinned).map((leaf) => leaf.key)
    expect(pinned).toEqual(['type', 'name'])
    expect(view.leaves.find((leaf) => leaf.key === 'name')?.identity).toBe(true)
    // Overview hides the Type column: only the Security identity remains pinned.
    const overview = buildPositionView('open-positions', 'overview', null, 'USD')
    expect(overview.leaves.filter((leaf) => leaf.pinned).map((leaf) => leaf.key)).toEqual(['name'])
  })

  it('sortability and alignment survive the metadata extension', () => {
    const open = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const leaf = (view, key) => view.leaves.find((l) => l.key === key)!
    expect(leaf(open, 'entry_value').sortable).toBe(true)
    expect(leaf(open, 'entry_value').align).toBe('end')
    expect(leaf(open, 'name').align).toBe('start')
    const closed = buildPositionView('closed-positions', 'full-ledger', null, 'USD')
    expect(leaf(closed, 'type').sortable).toBe(false)
  })
})

describe('unit metadata reacts to the committed reporting currency', () => {
  it('updates reporting-money unit labels and descriptions when the currency changes', () => {
    const usd = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const eur = buildPositionView('open-positions', 'full-ledger', null, 'EUR')
    const leaf = (view, key) => view.leaves.find((l) => l.key === key)!
    expect(leaf(usd, 'current_value').unitKind).toBe('reporting-money')
    expect(leaf(usd, 'current_value').unitLabel).toBe('USD')
    expect(leaf(eur, 'current_value').unitLabel).toBe('EUR')
    expect(leaf(usd, 'current_value').description).toContain('USD')
    expect(leaf(eur, 'current_value').description).toContain('EUR')
    for (const key of ['entry_value', 'realized_gl', 'unrealized_gl', 'total_return_amount']) {
      expect(leaf(usd, key).unitKind).toBe('reporting-money')
    }
  })

  it('keeps instrument prices in security-currency units regardless of reporting currency', () => {
    const leaf = (currency, key) =>
      buildPositionView('open-positions', 'full-ledger', null, currency)
        .leaves.find((l) => l.key === key)!
    for (const currency of ['USD', 'EUR']) {
      expect(leaf(currency, 'entry_price').unitKind).toBe('instrument-price')
      expect(leaf(currency, 'entry_price').unitLabel).toBe('security currency')
      expect(leaf(currency, 'entry_price').description).not.toContain(currency)
      // Bond percent-of-nominal semantics are described on the price leaves.
      expect(leaf(currency, 'entry_price').description).toMatch(/percentage of nominal/i)
      expect(leaf(currency, 'current_price').description).toMatch(/percentage of nominal/i)
    }
  })

  it('marks ratio and quantity unit kinds for their leaves', () => {
    const view = buildPositionView('open-positions', 'full-ledger', null, 'USD')
    const leaf = (key) => view.leaves.find((l) => l.key === key)!
    expect(leaf('share_of_portfolio').unitKind).toBe('ratio')
    expect(leaf('irr').unitKind).toBe('ratio')
    expect(leaf('current_position').unitKind).toBe('quantity')
    expect(leaf('investment_date').unitKind).toBe('date')
    expect(leaf('name').unitKind).toBe('identity')
  })
})

describe('group order is stable', () => {
  it('orders groups identity → entry → current/exit → performance', () => {
    expect(POSITION_GROUP_ORDER.indexOf('identity')).toBeLessThan(POSITION_GROUP_ORDER.indexOf('entry'))
    expect(POSITION_GROUP_ORDER.indexOf('entry')).toBeLessThan(POSITION_GROUP_ORDER.indexOf('performance'))
    expect(POSITION_GROUP_ORDER.indexOf('current')).toBeLessThan(POSITION_GROUP_ORDER.indexOf('performance'))
    expect(POSITION_GROUP_ORDER.indexOf('exit')).toBeLessThan(POSITION_GROUP_ORDER.indexOf('performance'))
  })
})
