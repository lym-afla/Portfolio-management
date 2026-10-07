// Renderer gate/capability policy (C3 NAV; C4 allocations and security
// histories). Each pilot is opt-in: only the exact release-flag string 'true'
// requests ECharts for that family, and even then only a validated v2 result
// may use it — legacy-only payloads always stay on Chart.js. The three gates
// are independent; C5 owns default-on rollout.
import type { NavResult } from './contracts'

export type Renderer = 'chartjs' | 'echarts'

export function pilotRequested(): boolean {
  return import.meta.env.VITE_NAV_ECHARTS_ENABLED === 'true'
}

export function allocationEchartsRequested(): boolean {
  return import.meta.env.VITE_ALLOCATION_ECHARTS_ENABLED === 'true'
}

export function securityEchartsRequested(): boolean {
  return import.meta.env.VITE_SECURITY_ECHARTS_ENABLED === 'true'
}

export function resolveRenderer(
  requested: Renderer,
  result: Pick<NavResult, 'capability'> | null,
): Renderer {
  if (requested !== 'echarts' || !result || result.capability !== 'v2') return 'chartjs'
  return 'echarts'
}
