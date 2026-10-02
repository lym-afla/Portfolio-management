// Pure runtime validation of chart contract v2 documents (C2). External input
// is read as unknown and validated into the typed ChartDocument family; no
// unchecked assertions, no date reconstruction from display labels, no value
// coercion. ISO dates are validated with an exclusive UTC year/month/day
// round-trip. Allocation and security document specifics are Task 2.
import type {
  ChartDocument,
  ChartPeriod,
  ChartSeries,
  ChartSeriesCategory,
  ChartUnit,
  ChartValue,
  LegacyNav,
  NavResult,
  ValueStatus,
} from './contracts'
import { ChartContractError, adaptLegacyNav } from './adaptLegacyNav'

const DECIMAL_PATTERN = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/
const VALUE_STATUSES: readonly ValueStatus[] = ['ok', 'partial', 'unknown', 'not_available', 'not_relevant']
const VALUE_REASONS = [
  'observed', 'zero_exposure', 'missing_price', 'missing_fx', 'omitted_valuation',
  'absent_unclassified', 'solver_unavailable', 'not_relevant',
] as const
const DOCUMENT_KINDS = ['nav', 'allocation', 'price', 'position'] as const
const DOCUMENT_OUTCOMES = ['ready', 'empty', 'partial'] as const
const DOCUMENT_PARTITIONS = ['complete', 'legacy_non_partitioning', 'unknown'] as const
const SERIES_METRICS = [
  'nav', 'category_nav', 'opening_nav', 'contributions', 'return', 'net_investments',
  'irr_inception', 'irr_interval', 'price', 'position',
] as const
const SERIES_AXES = ['money', 'return', 'price', 'quantity'] as const
const CATEGORY_KINDS = ['account_group', 'asset_type', 'asset_class', 'currency'] as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isDecimalString(value: unknown): value is string {
  return typeof value === 'string' && DECIMAL_PATTERN.test(value)
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return false
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const utc = new Date(Date.UTC(year, month - 1, day))
  return (
    utc.getUTCFullYear() === year && utc.getUTCMonth() === month - 1 && utc.getUTCDate() === day
  )
}

function member<T extends readonly string[]>(values: T, value: unknown, what: string): T[number] {
  if (typeof value !== 'string' || !(values as readonly string[]).includes(value)) {
    throw new ChartContractError(`Chart ${what} is invalid: ${String(value)}`)
  }
  return value as T[number]
}

function check(condition: boolean, message: string): void {
  if (!condition) throw new ChartContractError(message)
}

function parseChartValue(input: unknown, where: string): ChartValue {
  if (!isRecord(input)) throw new ChartContractError(`${where} must be an object`)
  const status = member(VALUE_STATUSES, input.status, `${where} status`)
  const reason = member(VALUE_REASONS, input.reason, `${where} reason`)
  if (typeof input.display !== 'string') {
    throw new ChartContractError(`${where} display must be a string`)
  }
  if (status === 'ok') {
    if (!isDecimalString(input.value) || !isDecimalString(input.plotValue)) {
      throw new ChartContractError(
        `${where} ok status requires decimal-string value and plotValue (raw type: ${typeof input.value})`
      )
    }
    if ('knownSubtotal' in input) {
      throw new ChartContractError(`${where} knownSubtotal is permitted only for partial values`)
    }
    return { value: input.value, plotValue: input.plotValue, status, reason, display: input.display }
  }
  if (input.value !== null || input.plotValue !== null) {
    throw new ChartContractError(`${where} status ${status} requires null value and plotValue`)
  }
  if ('knownSubtotal' in input) {
    if (status !== 'partial') {
      throw new ChartContractError(`${where} knownSubtotal is permitted only for partial values`)
    }
    if (!isDecimalString(input.knownSubtotal)) {
      throw new ChartContractError(`${where} knownSubtotal must be a decimal string`)
    }
    return { value: null, plotValue: null, knownSubtotal: input.knownSubtotal, status, reason, display: input.display }
  }
  return { value: null, plotValue: null, status, reason, display: input.display }
}

function parseChartUnit(input: unknown, axis: ChartSeries['axis'], where: string): ChartUnit {
  if (!isRecord(input)) throw new ChartContractError(`${where} unit must be an object`)
  const kind = input.kind
  switch (kind) {
    case 'money': {
      if (axis !== 'money' && axis !== 'price') {
        throw new ChartContractError(`${where} money unit does not match axis ${axis}`)
      }
      if (typeof input.currency !== 'string' || input.currency === '') {
        throw new ChartContractError(`${where} money unit requires a currency`)
      }
      if (input.plotDivisor !== '1' && input.plotDivisor !== '1000') {
        throw new ChartContractError(`${where} money unit plotDivisor must be '1' or '1000'`)
      }
      return { kind: 'money', currency: input.currency, plotDivisor: input.plotDivisor }
    }
    case 'ratio':
      if (axis !== 'return') throw new ChartContractError(`${where} ratio unit does not match axis ${axis}`)
      check(input.plotDivisor === '1', `${where} ratio unit plotDivisor must be '1'`)
      return { kind: 'ratio', plotDivisor: '1' }
    case 'quantity':
      if (axis !== 'quantity') throw new ChartContractError(`${where} quantity unit does not match axis ${axis}`)
      check(input.plotDivisor === '1', `${where} quantity unit plotDivisor must be '1'`)
      return { kind: 'quantity', plotDivisor: '1' }
    case 'percent_of_nominal':
      if (axis !== 'price') throw new ChartContractError(`${where} percent_of_nominal unit does not match axis ${axis}`)
      check(input.plotDivisor === '1', `${where} percent_of_nominal unit plotDivisor must be '1'`)
      return { kind: 'percent_of_nominal', plotDivisor: '1' }
    default:
      throw new ChartContractError(`${where} unit kind is invalid: ${String(kind)}`)
  }
}

function parseChartCategory(input: unknown, where: string): ChartSeriesCategory {
  if (!isRecord(input)) throw new ChartContractError(`${where} category must be an object`)
  const kind = member(CATEGORY_KINDS, input.kind, `${where} category kind`)
  const category: ChartSeriesCategory = { kind }
  if (input.code !== undefined) {
    if (typeof input.code !== 'string' || input.code === '') {
      throw new ChartContractError(`${where} category code must be a non-empty string`)
    }
    category.code = input.code
  }
  if (input.memberAccountIds !== undefined) {
    check(
      Array.isArray(input.memberAccountIds) &&
        input.memberAccountIds.length > 0 &&
        input.memberAccountIds.every((id) => Number.isInteger(id) && (id as number) > 0) &&
        new Set(input.memberAccountIds).size === input.memberAccountIds.length,
      `${where} memberAccountIds must be unique positive integers`
    )
    category.memberAccountIds = input.memberAccountIds as readonly number[]
  }
  return category
}

function parseChartSeries(input: unknown, periodCount: number, contextCurrency: string, index: number): ChartSeries {
  const where = `Chart series ${index}`
  if (!isRecord(input)) throw new ChartContractError(`${where} must be an object`)
  if (typeof input.id !== 'string' || input.id === '') {
    throw new ChartContractError(`${where} identity (id) must be a non-empty server-issued string`)
  }
  if (typeof input.label !== 'string') throw new ChartContractError(`${where} label must be a string`)
  const metric = member(SERIES_METRICS, input.metric, `${where} metric`)
  const role = member(['bar', 'line'] as const, input.role, `${where} role`)
  const axis = member(SERIES_AXES, input.axis, `${where} axis`)
  const unit = parseChartUnit(input.unit, axis, where)
  if (unit.kind === 'money' && unit.currency !== contextCurrency) {
    throw new ChartContractError(
      `${where} money unit currency ${unit.currency} does not match document currency ${contextCurrency}`
    )
  }
  if (!Array.isArray(input.points)) throw new ChartContractError(`${where} points must be an array`)
  if (input.points.length !== periodCount) {
    throw new ChartContractError(
      `${where} has ${input.points.length} points for ${periodCount} periods`
    )
  }
  const points = input.points.map((point, pointIndex) => parseChartValue(point, `${where} point ${pointIndex}`))
  const series: ChartSeries = { id: input.id, label: input.label, metric, role, axis, unit, points }
  if (input.category !== undefined) series.category = parseChartCategory(input.category, where)
  return series
}

function parseChartPeriod(input: unknown, index: number): ChartPeriod {
  const where = `Chart period ${index}`
  if (!isRecord(input)) throw new ChartContractError(`${where} must be an object`)
  if (typeof input.key !== 'string' || input.key === '') {
    throw new ChartContractError(`${where} identity (key) must be a non-empty server-issued string`)
  }
  if (!isIsoDate(input.endDate)) {
    throw new ChartContractError(`${where} date is invalid: ${String(input.endDate)}`)
  }
  if (typeof input.displayLabel !== 'string') {
    throw new ChartContractError(`${where} displayLabel must be a string`)
  }
  if (typeof input.partialPeriod !== 'boolean') {
    throw new ChartContractError(`${where} partialPeriod must be a boolean`)
  }
  const rawInterval = input.interval
  if (!isRecord(rawInterval)) throw new ChartContractError(`${where} interval must be an object`)
  const kind = member(['inception', 'sample_interval'] as const, rawInterval.kind, `${where} interval kind`)
  if (!isIsoDate(rawInterval.endDate)) {
    throw new ChartContractError(`${where} interval date is invalid: ${String(rawInterval.endDate)}`)
  }
  if (rawInterval.endDate !== input.endDate) {
    throw new ChartContractError(`${where} interval end does not equal its period end`)
  }
  let startDate: string | null = null
  if (kind === 'inception') {
    check(
      rawInterval.startDate === null,
      `${where} inception interval must keep its null first-point horizon start`
    )
  } else {
    if (!isIsoDate(rawInterval.startDate)) {
      throw new ChartContractError(`${where} interval date is invalid: ${String(rawInterval.startDate)}`)
    }
    if (rawInterval.startDate > rawInterval.endDate) {
      throw new ChartContractError(`${where} interval start follows its end`)
    }
    startDate = rawInterval.startDate
  }
  return {
    key: input.key,
    endDate: input.endDate,
    displayLabel: input.displayLabel,
    interval: { startDate, endDate: rawInterval.endDate, kind },
    partialPeriod: input.partialPeriod,
  }
}

function parseAccountSelection(input: unknown): ChartDocument['context']['accountSelection'] {
  if (!isRecord(input)) throw new ChartContractError('Chart context accountSelection must be an object')
  const type = String(input.type)
  if (type === 'all') {
    check(input.id === null, 'Chart context all-selection must carry a null id')
    return { type: 'all', id: null }
  }
  if (type === 'account' || type === 'broker' || type === 'group') {
    check(
      Number.isInteger(input.id) && (input.id as number) > 0,
      `Chart context selection ${type} requires a positive integer id`
    )
    return { type, id: input.id as number }
  }
  throw new ChartContractError(`Chart context accountSelection type is invalid: ${type}`)
}

function parseChartContext(input: unknown): ChartDocument['context'] {
  if (!isRecord(input)) throw new ChartContractError('Chart context must be an object')
  if (!isIsoDate(input.effectiveDate)) {
    throw new ChartContractError(`Chart context effectiveDate is invalid: ${String(input.effectiveDate)}`)
  }
  if (typeof input.currency !== 'string' || input.currency === '') {
    throw new ChartContractError('Chart context currency must be a non-empty string')
  }
  if (!Number.isInteger(input.digits) || (input.digits as number) < 0) {
    throw new ChartContractError(`Chart context digits is invalid: ${String(input.digits)}`)
  }
  if (!Array.isArray(input.accountIds) || !input.accountIds.every((id) => Number.isInteger(id) && (id as number) > 0)) {
    throw new ChartContractError('Chart context accountIds must be positive integers')
  }
  if (new Set(input.accountIds).size !== input.accountIds.length) {
    throw new ChartContractError('Chart context accountIds must be unique')
  }
  return {
    accountSelection: parseAccountSelection(input.accountSelection),
    accountIds: input.accountIds as readonly number[],
    effectiveDate: input.effectiveDate,
    currency: input.currency,
    digits: input.digits as number,
  }
}

/** Validate an unknown value into a typed ChartDocument or throw. */
export function parseChartDocument(input: unknown): ChartDocument {
  if (!isRecord(input)) throw new ChartContractError('Chart document must be an object')
  if (input.version !== 2) {
    throw new ChartContractError(`Unsupported chart contract version: ${String(input.version)}`)
  }
  const kind = member(DOCUMENT_KINDS, input.kind, 'document kind')
  const outcome = member(DOCUMENT_OUTCOMES, input.outcome, 'document outcome')
  const partition = member(DOCUMENT_PARTITIONS, input.partition, 'document partition')
  const context = parseChartContext(input.context)
  if (!Array.isArray(input.periods)) throw new ChartContractError('Chart periods must be an array')
  if (!Array.isArray(input.series)) throw new ChartContractError('Chart series must be an array')
  const periodKeys = new Set<string>()
  const periods = input.periods.map((period, index) => {
    const parsed = parseChartPeriod(period, index)
    if (periodKeys.has(parsed.key)) {
      throw new ChartContractError(`Chart period identity ${parsed.key} is duplicated`)
    }
    periodKeys.add(parsed.key)
    return parsed
  })
  const seriesIds = new Set<string>()
  const series = input.series.map((seriesInput, index) => {
    const parsed = parseChartSeries(seriesInput, periods.length, context.currency, index)
    if (seriesIds.has(parsed.id)) {
      throw new ChartContractError(`Chart series identity ${parsed.id} is duplicated`)
    }
    seriesIds.add(parsed.id)
    return parsed
  })
  if (outcome === 'empty' && (periods.length > 0 || series.length > 0)) {
    throw new ChartContractError('An empty chart document must not carry periods or series')
  }
  let totals: readonly ChartValue[] | undefined
  if (input.totals !== undefined) {
    if (!Array.isArray(input.totals)) throw new ChartContractError('Chart totals must be an array')
    if (input.totals.length !== periods.length) {
      throw new ChartContractError(`Chart totals length ${input.totals.length} does not match ${periods.length} periods`)
    }
    totals = input.totals.map((total, index) => parseChartValue(total, `Chart total ${index}`))
  }
  if (kind === 'nav' && series.length > 0) {
    for (const metric of ['irr_inception', 'irr_interval'] as const) {
      if (!series.some((entry) => entry.metric === metric)) {
        throw new ChartContractError(`Chart nav document must carry both IRR series; ${metric} is missing`)
      }
    }
  }
  const document: ChartDocument = { version: 2, kind, outcome, context, periods, series, partition }
  if (totals !== undefined) document.totals = totals
  return document
}

/** Validate a NAV endpoint envelope into the v2/legacy_only discriminant. */
export function parseNavEnvelope(input: unknown): NavResult {
  if (!isRecord(input)) throw new ChartContractError('NAV envelope must be an object')
  if (!('chartV2' in input)) {
    return { capability: 'legacy_only', legacy: adaptLegacyNav(input) }
  }
  if (input.chartV2 == null) {
    throw new ChartContractError('A present chartV2 must be a valid chart document, never a silent legacy downgrade')
  }
  let document: ChartDocument
  try {
    document = parseChartDocument(input.chartV2)
  } catch (error) {
    if (error instanceof ChartContractError) {
      throw new ChartContractError(`Invalid chartV2 document: ${error.message}`)
    }
    throw error
  }
  if (document.kind !== 'nav') {
    throw new ChartContractError(`NAV envelope carried a ${document.kind} document`)
  }
  const { chartV2: _modern, ...legacyRest } = input
  const legacy: LegacyNav = adaptLegacyNav(legacyRest)
  return { capability: 'v2', legacy, document }
}

export { ChartContractError }
