// Legacy NAV renderer payload validation (C2). The legacy wire contract is a
// visualization-only passthrough: dataset styling and extra fields survive
// unchanged, values are never coerced, and no modern identity or dates are
// invented from labels. 'N/A'/'N/R' unavailable markers stay strings.
import type { LegacyNav, LegacyNavDataset } from './contracts'

export class ChartContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ChartContractError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isLegacyDatum(value: unknown): value is number | string | null {
  return value === null || typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value))
}

function validateDataset(dataset: unknown, labelCount: number, index: number): LegacyNavDataset {
  if (!isRecord(dataset)) throw new ChartContractError(`Legacy dataset ${index} must be an object`)
  const { label, type, data } = dataset
  if (typeof label !== 'string' || label === '') {
    throw new ChartContractError(`Legacy dataset ${index} requires a non-empty label`)
  }
  if (type !== undefined && type !== 'bar' && type !== 'line') {
    throw new ChartContractError(`Legacy dataset ${index} has unsupported type ${String(type)}`)
  }
  if (!Array.isArray(data) || !data.every(isLegacyDatum)) {
    throw new ChartContractError(`Legacy dataset ${index} data must be numbers, strings or null`)
  }
  if (data.length !== labelCount) {
    throw new ChartContractError(
      `Legacy dataset ${label} length ${data.length} does not match ${labelCount} labels`
    )
  }
  return dataset as LegacyNavDataset
}

/** Validate the legacy renderer shape and return it losslessly. */
export function adaptLegacyNav(input: unknown): LegacyNav {
  if (!isRecord(input)) throw new ChartContractError('Legacy NAV payload must be an object')
  const { labels, datasets, currency } = input
  if (!Array.isArray(labels) || !labels.every((label): label is string => typeof label === 'string')) {
    throw new ChartContractError('Legacy NAV labels must be an array of strings')
  }
  if (!Array.isArray(datasets)) {
    throw new ChartContractError('Legacy NAV datasets must be an array')
  }
  if (typeof currency !== 'string' || currency === '') {
    throw new ChartContractError('Legacy NAV currency must be a non-empty string')
  }
  const validated = datasets.map((dataset, index) => validateDataset(dataset, labels.length, index))
  return { ...input, labels, datasets: validated } as unknown as LegacyNav
}
