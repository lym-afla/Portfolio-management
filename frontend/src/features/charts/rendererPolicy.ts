// Renderer gate/capability policy (C3). The pilot is opt-in: only the exact
// release-flag string 'true' requests ECharts, and even then only a validated
// v2 result may use it — legacy-only payloads always stay on Chart.js.
import type { NavResult } from './contracts'

export type Renderer = 'chartjs' | 'echarts'

export function pilotRequested(): boolean {
  return import.meta.env.VITE_NAV_ECHARTS_ENABLED === 'true'
}

export function resolveRenderer(
  requested: Renderer,
  result: Pick<NavResult, 'capability'> | null,
): Renderer {
  if (requested !== 'echarts' || !result || result.capability !== 'v2') return 'chartjs'
  return 'echarts'
}
