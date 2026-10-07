// Pure runtime validation of chart contract v2 documents (C2). External input
// is read as unknown and validated into the typed ChartDocument family; no
// unchecked assertions, no date reconstruction from display labels, no value
// coercion. ISO dates are validated with an exclusive UTC year/month/day
// round-trip. Allocation and security document specifics are Task 2.
import type {
  AllocationDocuments,
  AllocationResult,
  ChartAllocation,
  ChartAllocationSummary,
  ChartDocument,
  ChartPeriod,
  ChartSeries,
  ChartSeriesCategory,
  ChartUnit,
  ChartValue,
  LegacyBreakdown,
  LegacyBreakdownDimension,
  LegacyNav,
  LegacySecurityHistory,
  LegacySecurityRow,
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
const ALLOCATION_DIMENSIONS = ['asset_type', 'asset_class', 'currency'] as const
const PIE_ELIGIBILITIES = ['eligible', 'signed', 'nonpositive_total', 'incomplete', 'nonpartitioning'] as const

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
      if (axis === 'price' && input.plotDivisor !== '1') {
        throw new ChartContractError(`${where} price money unit plotDivisor must be '1'`)
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

function parseChartSeries(
  input: unknown,
  periodCount: number,
  contextCurrency: string | null,
  index: number
): ChartSeries {
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
  // NAV/allocation money is reporting currency; security instruments keep
  // their own trading currency, so no context match is enforced there.
  if (contextCurrency !== null && unit.kind === 'money' && unit.currency !== contextCurrency) {
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
  const seriesCurrencyCheck = kind === 'nav' || kind === 'allocation' ? context.currency : null
  const seriesIds = new Set<string>()
  const series = input.series.map((seriesInput, index) => {
    const parsed = parseChartSeries(seriesInput, periods.length, seriesCurrencyCheck, index)
    if (seriesIds.has(parsed.id)) {
      throw new ChartContractError(`Chart series identity ${parsed.id} is duplicated`)
    }
    seriesIds.add(parsed.id)
    return parsed
  })
  if (outcome === 'empty') {
    // Allocation keeps its single sampling period when empty; every other
    // kind has no periods. Price/position documents keep their identified
    // series with zero points (the backend always emits the series); nav and
    // allocation empties carry no series. Points already match the periods.
    if (periods.length > 0 && kind !== 'allocation') {
      throw new ChartContractError('An empty chart document must not carry periods')
    }
    if (series.length > 0 && (kind === 'nav' || kind === 'allocation')) {
      throw new ChartContractError(`An empty ${kind} document must not carry series`)
    }
  }
  let totals: readonly ChartValue[] | undefined
  if (input.totals !== undefined) {
    if (!Array.isArray(input.totals)) throw new ChartContractError('Chart totals must be an array')
    if (input.totals.length !== periods.length) {
      throw new ChartContractError(`Chart totals length ${input.totals.length} does not match ${periods.length} periods`)
    }
    totals = input.totals.map((total, index) => parseChartValue(total, `Chart total ${index}`))
  }
  let security: ChartDocument['security']
  if (input.security !== undefined) security = parseSecurity(input.security)
  else if (kind === 'price' || kind === 'position') {
    throw new ChartContractError(`Chart ${kind} document requires security identity`)
  }
  if (kind === 'price') {
    for (const entry of series) {
      if (entry.metric !== 'price' || entry.axis !== 'price') {
        throw new ChartContractError(`Chart price document series ${entry.id} must be metric price on the price axis`)
      }
    }
  }
  if (kind === 'position') {
    for (const entry of series) {
      if (entry.metric !== 'position' || entry.axis !== 'quantity') {
        throw new ChartContractError(`Chart position document series ${entry.id} must be metric position on the quantity axis`)
      }
    }
  }
  let allocations: readonly ChartAllocation[] | undefined
  if (input.allocations !== undefined) allocations = parseAllocations(input.allocations, seriesIds)
  let allocationSummary: ChartAllocationSummary | undefined
  if (input.allocationSummary !== undefined) {
    allocationSummary = parseAllocationSummary(input.allocationSummary, context.currency)
  }
  if (kind === 'allocation') {
    if (allocations === undefined || allocationSummary === undefined) {
      throw new ChartContractError('Chart allocation document requires allocations and allocationSummary')
    }
    validateAllocationConsistency(allocations, allocationSummary, partition, series)
  } else if (allocations !== undefined || allocationSummary !== undefined) {
    throw new ChartContractError('allocations and allocationSummary are permitted only for allocation documents')
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
  if (security !== undefined) document.security = security
  if (allocations !== undefined) document.allocations = allocations
  if (allocationSummary !== undefined) document.allocationSummary = allocationSummary
  return document
}

function parseAllocations(input: unknown, seriesIds: ReadonlySet<string>): readonly ChartAllocation[] {
  if (!Array.isArray(input)) throw new ChartContractError('Chart allocations must be an array')
  const referenced = new Set<string>()
  let previousRank = 0
  return input.map((allocation, index) => {
    const where = `Chart allocation ${index}`
    if (!isRecord(allocation)) throw new ChartContractError(`${where} must be an object`)
    if (typeof allocation.seriesId !== 'string' || !seriesIds.has(allocation.seriesId)) {
      throw new ChartContractError(
        `Chart allocation references an unknown series: ${String(allocation.seriesId)}`
      )
    }
    if (referenced.has(allocation.seriesId)) {
      throw new ChartContractError(`Chart allocation references series ${allocation.seriesId} twice`)
    }
    referenced.add(allocation.seriesId)
    if (!Number.isInteger(allocation.rank) || (allocation.rank as number) < 1) {
      throw new ChartContractError(`${where} rank must be a positive integer`)
    }
    if ((allocation.rank as number) <= previousRank) {
      throw new ChartContractError(
        `${where} rank ${String(allocation.rank)} does not follow the previous rank ${previousRank} in server order`
      )
    }
    previousRank = allocation.rank as number
    return {
      seriesId: allocation.seriesId,
      rank: allocation.rank as number,
      amount: parseChartValue(allocation.amount, `${where} amount`),
      share: parseChartValue(allocation.share, `${where} share`),
    }
  })
}

function parseAllocationSummary(input: unknown, contextCurrency: string): ChartAllocationSummary {
  if (!isRecord(input)) throw new ChartContractError('Chart allocationSummary must be an object')
  const dimension = member(ALLOCATION_DIMENSIONS, input.dimension, 'allocationSummary dimension')
  const unit = parseChartUnit(input.unit, 'money', 'allocationSummary unit')
  if (unit.kind !== 'money' || unit.plotDivisor !== '1') {
    throw new ChartContractError('allocationSummary unit must be reporting money with plotDivisor 1')
  }
  if (unit.currency !== contextCurrency) {
    throw new ChartContractError(
      `allocationSummary unit currency ${unit.currency} does not match document currency ${contextCurrency}`
    )
  }
  return {
    dimension,
    unit,
    denominator: parseChartValue(input.denominator, 'allocationSummary denominator'),
    totalShare: parseChartValue(input.totalShare, 'allocationSummary totalShare'),
    pieEligibility: member(PIE_ELIGIBILITIES, input.pieEligibility, 'allocationSummary pieEligibility'),
  }
}

function parseSecurity(input: unknown): { id: number; instrumentType: string } {
  if (!isRecord(input)) throw new ChartContractError('Chart security must be an object')
  if (!Number.isInteger(input.id) || (input.id as number) <= 0) {
    throw new ChartContractError('Chart security id must be a positive integer')
  }
  if (typeof input.instrumentType !== 'string' || input.instrumentType === '') {
    throw new ChartContractError('Chart security instrumentType must be a non-empty string')
  }
  return { id: input.id as number, instrumentType: input.instrumentType }
}

// Backend ownership of arithmetic certification: the adapter checks structural
// consistency only and never sums amounts or recalculates shares.
function validateAllocationConsistency(
  allocations: readonly ChartAllocation[],
  summary: ChartAllocationSummary,
  partition: ChartDocument['partition'],
  series: readonly ChartSeries[],
): void {
  const byId = new Map(series.map((entry) => [entry.id, entry]))
  if (allocations.length !== series.length) {
    throw new ChartContractError(
      `Chart allocation document references ${allocations.length} of ${series.length} category series`
    )
  }
  for (const allocation of allocations) {
    const referenced = byId.get(allocation.seriesId)!
    if (referenced.metric !== 'category_nav') {
      throw new ChartContractError(
        `Chart allocation series ${allocation.seriesId} must be metric category_nav`
      )
    }
    if (referenced.category?.kind !== summary.dimension) {
      throw new ChartContractError(
        `Chart allocation series ${allocation.seriesId} category kind does not match dimension ${summary.dimension}`
      )
    }
    if (referenced.unit.kind !== 'money' || referenced.unit.plotDivisor !== '1') {
      throw new ChartContractError('Allocation category series must use reporting money with plotDivisor 1')
    }
  }
  if (summary.pieEligibility === 'eligible') {
    if (partition !== 'complete') {
      throw new ChartContractError('An eligible pie claim requires partition complete')
    }
    if (summary.denominator.status !== 'ok' || summary.totalShare.status !== 'ok') {
      throw new ChartContractError('An eligible pie claim requires ok denominator and totalShare')
    }
    for (const allocation of allocations) {
      if (allocation.amount.status !== 'ok' || allocation.share.status !== 'ok') {
        throw new ChartContractError('An eligible pie claim requires ok contributing amounts and shares')
      }
    }
  }
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

// ---- C4: breakdown and security history envelopes --------------------------

/** The v2 dimension map of the breakdown endpoint: response key → document dimension. */
const ALLOCATION_DIMENSION_KEYS = {
  assetType: 'asset_type',
  assetClass: 'asset_class',
  currency: 'currency',
} as const

function parseLegacyBreakdownDimension(input: unknown, where: string): LegacyBreakdownDimension {
  if (!isRecord(input)) throw new ChartContractError(`${where} must be an object`)
  for (const field of ['data', 'percentage'] as const) {
    const record = input[field]
    if (!isRecord(record)) throw new ChartContractError(`${where} ${field} must be an object`)
    for (const [key, value] of Object.entries(record)) {
      if (typeof value !== 'string') {
        throw new ChartContractError(`${where} ${field}.${key} must be a string, never coerced`)
      }
    }
  }
  return {
    data: input.data as LegacyBreakdownDimension['data'],
    percentage: input.percentage as LegacyBreakdownDimension['percentage'],
  }
}

function parseLegacyBreakdown(input: unknown): LegacyBreakdown {
  if (!isRecord(input)) throw new ChartContractError('Legacy breakdown payload must be an object')
  const legacy: LegacyBreakdown = {
    ...input,
    assetType: parseLegacyBreakdownDimension(input.assetType, 'Legacy assetType'),
    assetClass: parseLegacyBreakdownDimension(input.assetClass, 'Legacy assetClass'),
    currency: parseLegacyBreakdownDimension(input.currency, 'Legacy currency'),
    totalNAV: typeof input.totalNAV === 'string' ? input.totalNAV : (() => {
      throw new ChartContractError('Legacy breakdown totalNAV must be a string')
    })(),
  }
  return legacy
}

/** Validate the breakdown envelope: one request, three allocation documents. */
export function parseAllocationEnvelope(input: unknown): AllocationResult {
  if (!isRecord(input)) throw new ChartContractError('Breakdown envelope must be an object')
  const legacy = parseLegacyBreakdown(input)
  if (!('chartV2' in input)) {
    return { capability: 'legacy_only', legacy }
  }
  const rawDocuments = input.chartV2
  if (rawDocuments == null) {
    throw new ChartContractError('A present chartV2 must carry all three allocation documents, never a silent downgrade')
  }
  if (!isRecord(rawDocuments)) throw new ChartContractError('Breakdown chartV2 must be an object of allocation documents')
  const documents = {} as AllocationDocuments
  for (const key of Object.keys(ALLOCATION_DIMENSION_KEYS) as (keyof typeof ALLOCATION_DIMENSION_KEYS)[]) {
    const parsed = parseEnvelopeDocument(rawDocuments[key], 'allocation', `Breakdown chartV2.${key}`)
    const dimension = parsed.allocationSummary?.dimension
    if (dimension !== ALLOCATION_DIMENSION_KEYS[key]) {
      throw new ChartContractError(
        `Breakdown chartV2.${key} carried dimension ${String(dimension)} instead of ${ALLOCATION_DIMENSION_KEYS[key]}`
      )
    }
    documents[key] = parsed
  }
  for (const extraKey of Object.keys(rawDocuments)) {
    if (!(extraKey in ALLOCATION_DIMENSION_KEYS)) {
      throw new ChartContractError(`Breakdown chartV2 carried an unexpected dimension ${extraKey}`)
    }
  }
  return { capability: 'v2', legacy, documents }
}

function parseEnvelopeDocument(
  input: unknown,
  kind: 'allocation' | 'price' | 'position',
  where: string,
): ChartDocument {
  let document: ChartDocument
  try {
    document = parseChartDocument(input)
  } catch (error) {
    if (error instanceof ChartContractError) {
      throw new ChartContractError(`Invalid chartV2 document (${where}): ${error.message}`)
    }
    throw error
  }
  if (document.kind !== kind) {
    throw new ChartContractError(`${where} carried a ${document.kind} document instead of ${kind}`)
  }
  return document
}

function parseLegacySecurityHistory(input: unknown, kind: 'price' | 'position'): LegacySecurityHistory {
  if (!Array.isArray(input)) {
    throw new ChartContractError(`Legacy ${kind} history must be an array`)
  }
  return input.map((row, index): LegacySecurityRow => {
    if (!isRecord(row)) throw new ChartContractError(`Legacy ${kind} row ${index} must be an object`)
    if (typeof row.date !== 'string') {
      throw new ChartContractError(`Legacy ${kind} row ${index} date must be a string`)
    }
    if (kind === 'price') {
      if (typeof row.price !== 'number' || !Number.isFinite(row.price)) {
        throw new ChartContractError(`Legacy price row ${index} price must be a finite number`)
      }
    } else if (typeof row.position !== 'string') {
      throw new ChartContractError(`Legacy position row ${index} position must be a string`)
    }
    return row as LegacySecurityRow
  })
}

/** Validate a security history envelope against the endpoint's own legacy shape. */
export function parseSecurityEnvelope(
  input: unknown,
  kind: 'price' | 'position',
): { capability: 'v2'; legacy: LegacySecurityHistory; document: ChartDocument } | { capability: 'legacy_only'; legacy: LegacySecurityHistory } {
  // The pre-v2 wire of both security endpoints is a bare JSON array.
  if (Array.isArray(input)) {
    return { capability: 'legacy_only', legacy: parseLegacySecurityHistory(input, kind) }
  }
  if (!isRecord(input)) throw new ChartContractError(`Security ${kind} envelope must be an array or an object`)
  if (!('chartV2' in input)) {
    throw new ChartContractError(`Security ${kind} envelope carried an unrecognized object without chartV2`)
  }
  const legacy = parseLegacySecurityHistory(input.legacy, kind)
  if (input.chartV2 == null) {
    throw new ChartContractError('A present chartV2 must be a valid chart document, never a silent legacy downgrade')
  }
  const document = parseEnvelopeDocument(input.chartV2, kind, `Security ${kind} chartV2`)
  return { capability: 'v2', legacy, document }
}

export { ChartContractError }
