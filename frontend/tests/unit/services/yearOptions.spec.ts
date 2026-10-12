// Task 2 (real-data corrections): getYearOptions must match the real backend
// wire (common/views.py get_year_options_api) — numeric years as {text,value}
// strings, a {divider: true} separator, and the special All-time/YTD ranges —
// instead of demanding an integer array that real responses never satisfy.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const transport = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/services/http/client', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, apiGet: transport.apiGet }
})

import { calendarYearOptions, getYearOptions } from '@/services/api/database'

const REAL_WIRE = {
  table_years: [
    { text: '2026', value: '2026' },
    { text: '2025', value: '2025' },
    { divider: true },
    { text: 'All-time', value: 'all_time' },
    { text: '2026YTD', value: 'ytd' },
  ],
}

beforeEach(() => {
  transport.apiGet.mockReset()
})

describe('getYearOptions (real wire adapter)', () => {
  it('adapts the real mixed wire: years, divider and special ranges', async () => {
    transport.apiGet.mockResolvedValue(REAL_WIRE)
    const options = await getYearOptions()
    expect(options).toEqual([
      { text: '2026', value: '2026' },
      { text: '2025', value: '2025' },
      { divider: true, text: '', value: '' },
      { text: 'All-time', value: 'all_time' },
      { text: '2026YTD', value: 'ytd' },
    ])
  })

  it('rejects malformed entries instead of silently dropping them', async () => {
    transport.apiGet.mockResolvedValue({ table_years: [{ text: '2026' }, { junk: true }] })
    await expect(getYearOptions()).rejects.toThrow('Invalid year options response')
  })

  it('rejects a non-list response', async () => {
    transport.apiGet.mockResolvedValue({ table_years: '2026' })
    await expect(getYearOptions()).rejects.toThrow('Invalid year options response')
  })
})

describe('calendarYearOptions (summary breakdown selector)', () => {
  it('offers only the calendar years the summary endpoint supports', () => {
    const options = calendarYearOptions([
      { text: '2026', value: '2026' },
      { text: '2025', value: '2025' },
      { divider: true, text: '', value: '' },
      { text: 'All-time', value: 'all_time' },
      { text: '2026YTD', value: 'ytd' },
    ])
    expect(options).toEqual([
      { text: '2026', value: '2026' },
      { text: '2025', value: '2025' },
    ])
  })
})
