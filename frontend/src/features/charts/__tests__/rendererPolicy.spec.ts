// C5a Task 2: deterministic default-on release policy. The reviewed
// candidate treats an ABSENT flag as enabled; an explicit 'true' enables,
// an explicit 'false' disables, and ANY other supplied value — including
// the empty string — conservatively disables. This deliberately supersedes
// the C3/C4 opt-in defaults in this candidate only. The three family gates
// stay independent and legacy-only payloads always stay on Chart.js.
import { afterEach, describe, expect, it } from 'vitest'
import type { NavResult } from '../contracts'
import {
  allocationEchartsRequested,
  chartFlagEnabled,
  pilotRequested,
  resolveRenderer,
  securityEchartsRequested,
} from '../rendererPolicy'

const FLAG_NAMES = {
  nav: 'VITE_NAV_ECHARTS_ENABLED',
  allocation: 'VITE_ALLOCATION_ECHARTS_ENABLED',
  security: 'VITE_SECURITY_ECHARTS_ENABLED',
} as const

type Family = keyof typeof FLAG_NAMES

function setFlag(family: Family, value: string | undefined): void {
  if (value === undefined) delete import.meta.env[FLAG_NAMES[family]]
  else import.meta.env[FLAG_NAMES[family]] = value
}

const REQUESTED: Record<Family, () => boolean> = {
  nav: pilotRequested,
  allocation: allocationEchartsRequested,
  security: securityEchartsRequested,
}

function v2Result(): NavResult {
  return {
    capability: 'v2',
    legacy: { labels: [], currency: 'USDk', datasets: [] },
    document: {
      version: 2, kind: 'nav', outcome: 'ready', partition: 'complete',
      context: { accountSelection: { type: 'all', id: null }, accountIds: [], effectiveDate: '2026-01-31', currency: 'USD', digits: 2 },
      periods: [], series: [],
    },
  }
}

function legacyOnlyResult(): NavResult {
  return { capability: 'legacy_only', legacy: { labels: [], currency: 'USDk', datasets: [] } }
}

afterEach(() => {
  for (const name of Object.values(FLAG_NAMES)) delete import.meta.env[name]
})

describe('chartFlagEnabled value classes', () => {
  const cases: Array<[string | undefined, boolean, string]> = [
    [undefined, true, 'absent means the reviewed default-on candidate'],
    ['true', true, 'exact true enables'],
    ['false', false, 'exact false is the rollback override'],
    ['', false, 'an empty value is conservative off'],
    ['TRUE', false, 'uppercase is not the exact true token'],
    ['True', false, 'mixed case is not the exact true token'],
    ['true ', false, 'trailing whitespace is not the exact token'],
    [' true', false, 'leading whitespace is not the exact token'],
    ['0', false, 'numeric strings are not the exact token'],
    ['1', false, 'numeric strings are not the exact token'],
    ['yes', false, 'truthy words are not the exact token'],
    ['enabled', false, 'arbitrary values are conservative off'],
  ]

  for (const [value, expected, label] of cases) {
    it(`treats ${value === undefined ? 'undefined' : JSON.stringify(value)} as ${expected} (${label})`, () => {
      expect(chartFlagEnabled(value)).toBe(expected)
    })
  }
})

describe('independent family gates', () => {
  for (const family of Object.keys(FLAG_NAMES) as Family[]) {
    it(`${family} reads its own flag: absent -> true, 'true' -> true, 'false' -> false, '' -> false`, () => {
      for (const [value, expected] of [[undefined, true], ['true', true], ['false', false], ['', false]] as const) {
        setFlag('nav', 'true')
        setFlag('allocation', 'true')
        setFlag('security', 'true')
        setFlag(family, value)
        expect(REQUESTED[family]()).toBe(expected)
      }
    })
  }

  it('keeps the families independent across all eight boolean combinations', () => {
    for (const nav of [true, false]) {
      for (const allocation of [true, false]) {
        for (const security of [true, false]) {
          setFlag('nav', nav ? 'true' : 'false')
          setFlag('allocation', allocation ? 'true' : 'false')
          setFlag('security', security ? 'true' : 'false')
          expect(pilotRequested()).toBe(nav)
          expect(allocationEchartsRequested()).toBe(allocation)
          expect(securityEchartsRequested()).toBe(security)
        }
      }
    }
  })

  it('absent flags default every family on simultaneously (the release candidate)', () => {
    setFlag('nav', undefined)
    setFlag('allocation', undefined)
    setFlag('security', undefined)
    expect(pilotRequested()).toBe(true)
    expect(allocationEchartsRequested()).toBe(true)
    expect(securityEchartsRequested()).toBe(true)
  })
})

describe('capability resolution is unchanged', () => {
  it('keeps legacy-only payloads on Chart.js even when every gate is on', () => {
    setFlag('nav', undefined)
    setFlag('allocation', undefined)
    setFlag('security', undefined)
    expect(resolveRenderer('echarts', legacyOnlyResult())).toBe('chartjs')
  })

  it('keeps legacy-only payloads on Chart.js when gates are explicitly off', () => {
    setFlag('nav', 'false')
    expect(resolveRenderer('chartjs', legacyOnlyResult())).toBe('chartjs')
  })

  it('allows ECharts only for validated v2 results with the gate requested', () => {
    expect(resolveRenderer('echarts', v2Result())).toBe('echarts')
    expect(resolveRenderer('chartjs', v2Result())).toBe('chartjs')
  })

  it('answers chartjs for a null result regardless of the request', () => {
    expect(resolveRenderer('echarts', null)).toBe('chartjs')
  })

  it('never lets a present-invalid v2 object reach the modern renderer', () => {
    // The parser rejects malformed documents upstream: a result reaching the
    // policy is either a validated v2 document or an honest legacy_only
    // capability. Anything that is not a validated v2 result — including a
    // present-but-invalid object that could only arrive through a parser
    // defect — resolves to Chart.js and can never masquerade as a
    // successful legacy response.
    const notV2 = { capability: 'legacy_only' } as unknown as NavResult
    expect(resolveRenderer('echarts', notV2)).toBe('chartjs')
  })
})
