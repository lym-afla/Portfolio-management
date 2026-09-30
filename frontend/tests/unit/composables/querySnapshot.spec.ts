import { expect, it } from 'vitest'
import { snapshotTableQuery } from '@/types/query'
import type { TableQueryParams } from '@/types/query'

it('captures immutable account and sort values separately from caller-owned objects', () => {
  const selection = { type: 'account' as const, id: 1 }
  const sortBy = { key: 'name', order: 'asc' as const }
  const params: TableQueryParams = {
    context: { revision: 1, accountSelection: selection, effectiveCurrentDate: '2026-09-08', currency: 'USD', digits: 2 },
    dateFrom: null, dateTo: '2026-09-08', page: 1, itemsPerPage: 25, search: 'EUR', sortBy,
  }
  const captured = snapshotTableQuery(params)
  selection.id = 2
  sortBy.key = 'price'
  expect(captured.context.accountSelection.id).toBe(1)
  expect(captured.sortBy.key).toBe('name')
  expect(Object.isFrozen(captured)).toBe(true)
  expect(Object.isFrozen(captured.context.accountSelection)).toBe(true)
  expect(Object.isFrozen(captured.sortBy)).toBe(true)
})
