import { beforeEach, expect, it } from 'vitest'

import { createMemoryStorage } from '../helpers/memoryStorage'

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: createMemoryStorage(),
  })
})

it('supports the browser storage API without native Node persistence', () => {
  localStorage.setItem('accountSelection', '{"type":"all","id":null}')

  expect(localStorage.getItem('accountSelection')).toContain('"all"')
  expect(localStorage.length).toBe(1)
  expect(localStorage.key(0)).toBe('accountSelection')
  expect(localStorage.key(1)).toBeNull()

  localStorage.removeItem('accountSelection')
  expect(localStorage.getItem('accountSelection')).toBeNull()
})

it('starts each test with empty storage', () => {
  expect(localStorage.length).toBe(0)
})

it('stringifies keys and values and supports clear', () => {
  const browserRuntimeStorage = localStorage as unknown as {
    setItem(key: unknown, value: unknown): void
  }
  browserRuntimeStorage.setItem(1, null)
  browserRuntimeStorage.setItem('second', 2)

  expect(localStorage.getItem('1')).toBe('null')
  expect(localStorage.getItem('second')).toBe('2')

  localStorage.clear()
  expect(localStorage.length).toBe(0)
})
