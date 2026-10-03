// The sole decimal-string to JS-number plotting boundary (C3). This is an
// explicit rendering approximation, never a reusable financial utility: no
// sums, unit conversion, rescaling or re-division happens here, and the
// validated point (with its exact strings) stays authoritative in state.
import type { ChartValue } from './contracts'

export function toPlotNumber(point: ChartValue): number | null {
  if (point.status !== 'ok' || point.plotValue === null) return null
  const value = Number(point.plotValue)
  if (!Number.isFinite(value)) throw new RangeError('Chart value exceeds plotting range')
  return value
}
