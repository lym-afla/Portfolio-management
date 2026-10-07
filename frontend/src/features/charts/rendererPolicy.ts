// Renderer gate/capability policy (C3 NAV; C4 allocations and security
// histories; C5a deterministic default-on release candidate).
//
// Release-flag grammar (C5a): an ABSENT flag means the reviewed default-on
// candidate, the exact string 'true' enables, the exact string 'false' is
// the rollback override, and ANY other supplied value — including the empty
// string — conservatively disables. This deliberately supersedes the C3/C4
// opt-in defaults in this candidate only. The three family gates are
// independent, values are read at BUILD time (changing a flag requires
// rebuild/redeploy; these are not runtime kill switches), and even a
// requested gate only selects ECharts for a validated v2 result —
// legacy-only payloads always stay on Chart.js.
import type { NavResult } from './contracts'

export type Renderer = 'chartjs' | 'echarts'

export function chartFlagEnabled(value: string | undefined): boolean {
  if (value === undefined) return true
  if (value === 'true') return true
  if (value === 'false') return false
  return false
}

export function pilotRequested(): boolean {
  return chartFlagEnabled(import.meta.env.VITE_NAV_ECHARTS_ENABLED)
}

export function allocationEchartsRequested(): boolean {
  return chartFlagEnabled(import.meta.env.VITE_ALLOCATION_ECHARTS_ENABLED)
}

export function securityEchartsRequested(): boolean {
  return chartFlagEnabled(import.meta.env.VITE_SECURITY_ECHARTS_ENABLED)
}

export function resolveRenderer(
  requested: Renderer,
  result: Pick<NavResult, 'capability'> | null,
): Renderer {
  if (requested !== 'echarts' || !result || result.capability !== 'v2') return 'chartjs'
  return 'echarts'
}
