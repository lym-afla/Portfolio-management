import { ApiError } from '@/services/http/errors'
import { apiGet, type RequestOptions } from '@/services/http/client'
import { isRecord, type DisplayValue } from '@/types/portfolioTables'

export interface DashboardSummary extends Record<string, unknown> {
  'Current NAV': DisplayValue
  Invested: DisplayValue
  'Cash-out': DisplayValue
  total_return: DisplayValue
  irr: DisplayValue
}
const metricKeys = ['Current NAV', 'Invested', 'Cash-out', 'total_return', 'irr'] as const
export function decodeDashboardSummary(value: unknown): DashboardSummary {
  if (!isRecord(value) || !metricKeys.every((key) => typeof value[key] === 'string' || value[key] === null)) {
    throw new ApiError('Invalid dashboard summary response')
  }
  return value as DashboardSummary
}

// ---------------------------------------------------------------------------
// Opt-in summary contract v2: the reconciled statement document. The request
// stays the dashboard's single summary fetch; the response carries the legacy
// five fields unchanged plus the additive ``summaryV2`` document. A present-
// but-invalid document is an error, never a silent downgrade, and the
// document context must match the captured request context (the established
// chart-context conventions).
// ---------------------------------------------------------------------------

export type StatementStatus = 'ok' | 'partial' | 'unavailable'

export interface StatementAmount {
  raw: string | null
  display: string
  status: StatementStatus
  reason?: string
  knownSubtotal?: string
}

export interface StatementReturn {
  value: string | null
  display: string
  status: 'ok' | 'partial' | 'not_available' | 'not_relevant'
  reason: string
}

export interface StatementContext {
  accountSelection: { type: string; id: number | null }
  accountIds: number[]
  effectiveDate: string
  currency: string
  digits: number
}

export interface ReconciledStatement {
  version: number
  kind: string
  context: StatementContext
  status: 'complete' | 'partial' | 'unavailable'
  reasons: string[]
  capital: {
    invested: StatementAmount
    cashOut: StatementAmount
    netInvestedCapital: StatementAmount
  }
  netResult: {
    nav: StatementAmount
    controlTotal: StatementAmount
    components: {
      realizedPrice: StatementAmount
      unrealizedPrice: StatementAmount
      income: StatementAmount
      fees: StatementAmount
      taxes: StatementAmount
      fx: StatementAmount
      otherFlows: StatementAmount
    }
    fxDetail: { security: StatementAmount; cashFlows: StatementAmount }
    attributedSum: StatementAmount
    unexplainedDifference: StatementAmount
    toleranceRaw: string
    toleranceBasis: string
    reconciliation: 'reconciled' | 'unreconciled' | 'incomplete'
  }
  returns: { totalReturn: StatementReturn; irr: StatementReturn }
  diagnostics: {
    omittedValuations: Record<string, unknown>[]
    unclassifiedInKindFlows: {
      present: boolean
      count: number
      signedFmv?: string
      fmvKnown?: boolean
    }
    notes: string[]
  }
}

export type DashboardSummaryResult =
  | { capability: 'v2'; legacy: DashboardSummary; statement: ReconciledStatement }
  // An older backend ignoring the negotiation parameter answers with the
  // legacy payload alone; the UI keeps the five metrics with an honest
  // unavailable-breakdown notice.
  | { capability: 'legacy_only'; legacy: DashboardSummary }

/** The captured request context the response must agree with. */
export interface CapturedSummaryContext {
  accountSelection: { type: string; id: number | null }
  effectiveCurrentDate: string
  currency: string
  digits: number
}

/** The response disagrees with the captured request context. */
export class SummaryContextMismatchError extends ApiError {
  constructor(message: string, status?: number) {
    super(message, status)
    this.name = 'SummaryContextMismatchError'
  }
}

function invalid(field: string): ApiError {
  return new ApiError(`Invalid dashboard statement response: ${field}`)
}

// Exact fixed-point decimal notation: optional sign, digits, optional
// fraction. Never scientific, never NaN/Infinity, never blank.
const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$|^0$/
const DATE_PATTERN = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/

function isDecimalString(value: unknown): value is string {
  return typeof value === 'string' && DECIMAL_PATTERN.test(value)
}

function isIsoDateString(value: unknown): value is string {
  if (typeof value !== 'string' || !DATE_PATTERN.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(value)
}

function decodeAmount(value: unknown, field: string): StatementAmount {
  if (!isRecord(value) || typeof value.display !== 'string' || value.display === '') {
    throw invalid(field)
  }
  const status = value.status
  if (status !== 'ok' && status !== 'partial' && status !== 'unavailable') {
    throw invalid(`${field}.status`)
  }
  if (value.raw !== null && !isDecimalString(value.raw)) {
    throw invalid(`${field}.raw`)
  }
  // Status coherence: an ok amount is a certified number; an unavailable
  // amount carries no number at all; partial may carry its known value.
  if (status === 'ok' && value.raw === null) throw invalid(`${field}.raw`)
  if (status === 'unavailable' && value.raw !== null) throw invalid(`${field}.raw`)
  if (value.reason !== undefined && typeof value.reason !== 'string') {
    throw invalid(`${field}.reason`)
  }
  if (value.knownSubtotal !== undefined) {
    if (status !== 'partial') throw invalid(`${field}.knownSubtotal`)
    if (!isDecimalString(value.knownSubtotal)) throw invalid(`${field}.knownSubtotal`)
  }
  const amount: StatementAmount = {
    raw: (value.raw ?? null) as string | null,
    display: value.display,
    status,
  }
  if (value.reason !== undefined) amount.reason = value.reason as string
  if (value.knownSubtotal !== undefined) amount.knownSubtotal = value.knownSubtotal as string
  return amount
}

function decodeReturn(value: unknown, field: string): StatementReturn {
  if (
    !isRecord(value) ||
    typeof value.display !== 'string' ||
    typeof value.reason !== 'string' ||
    (value.value !== null && !isDecimalString(value.value))
  ) {
    throw invalid(field)
  }
  const status = value.status
  if (status !== 'ok' && status !== 'partial' && status !== 'not_available' && status !== 'not_relevant') {
    throw invalid(`${field}.status`)
  }
  // Status/value coherence: a certified return carries a number; a terminal
  // (not_available / not_relevant) return never does.
  if (status === 'ok' && value.value === null) throw invalid(`${field}.value`)
  if ((status === 'not_available' || status === 'not_relevant') && value.value !== null) {
    throw invalid(`${field}.value`)
  }
  return {
    value: (value.value ?? null) as string | null,
    display: value.display,
    status,
    reason: value.reason,
  }
}

function decodeSelection(value: unknown): { type: string; id: number | null } {
  if (!isRecord(value)) throw invalid('context.accountSelection')
  const type = value.type
  if (type !== 'all' && type !== 'account' && type !== 'broker' && type !== 'group') {
    throw invalid('context.accountSelection.type')
  }
  if (type === 'all') {
    if (value.id !== null) throw invalid('context.accountSelection.id')
    return { type, id: null }
  }
  if (typeof value.id !== 'number' || !Number.isInteger(value.id) || value.id < 0) {
    throw invalid('context.accountSelection.id')
  }
  return { type, id: value.id }
}

function decodeStatement(value: unknown): ReconciledStatement {
  if (!isRecord(value) || value.version !== 2 || value.kind !== 'statement') {
    throw invalid('version/kind')
  }
  const context = value.context
  if (!isRecord(context)) throw invalid('context')
  const accountSelection = decodeSelection(context.accountSelection)
  if (!isIsoDateString(context.effectiveDate)) throw invalid('context.effectiveDate')
  if (typeof context.currency !== 'string' || context.currency === '') {
    throw invalid('context.currency')
  }
  if (
    typeof context.digits !== 'number' ||
    !Number.isInteger(context.digits) ||
    context.digits < 0 ||
    context.digits > 9
  ) {
    throw invalid('context.digits')
  }
  const accountIds = context.accountIds
  if (
    !Array.isArray(accountIds) ||
    !accountIds.every((id) => typeof id === 'number' && Number.isInteger(id) && id >= 0)
  ) {
    throw invalid('context.accountIds')
  }
  if (value.status !== 'complete' && value.status !== 'partial' && value.status !== 'unavailable') {
    throw invalid('status')
  }
  if (!Array.isArray(value.reasons) || !value.reasons.every((reason) => typeof reason === 'string')) {
    throw invalid('reasons')
  }
  const capital = value.capital
  const netResult = value.netResult
  const components = isRecord(netResult) ? netResult.components : undefined
  const fxDetail = isRecord(netResult) ? netResult.fxDetail : undefined
  const returns = value.returns
  const diagnostics = value.diagnostics
  if (!isRecord(capital)) throw invalid('capital')
  if (!isRecord(netResult) || !isRecord(components) || !isRecord(fxDetail)) {
    throw invalid('netResult')
  }
  if (
    netResult.reconciliation !== 'reconciled' &&
    netResult.reconciliation !== 'unreconciled' &&
    netResult.reconciliation !== 'incomplete'
  ) {
    throw invalid('reconciliation')
  }
  // Status coherence: a complete statement is a reconciled one and vice
  // versa; an unavailable scope can never claim reconciliation.
  if (value.status === 'complete' && netResult.reconciliation !== 'reconciled') {
    throw invalid('status/reconciliation')
  }
  if (netResult.reconciliation === 'reconciled' && value.status !== 'complete') {
    throw invalid('status/reconciliation')
  }
  if (value.status === 'unavailable' && netResult.reconciliation !== 'incomplete') {
    throw invalid('status/reconciliation')
  }
  if (!isDecimalString(netResult.toleranceRaw)) throw invalid('toleranceRaw')
  if (typeof netResult.toleranceBasis !== 'string') throw invalid('toleranceBasis')
  if (!isRecord(returns) || !isRecord(diagnostics) || !Array.isArray(diagnostics.omittedValuations)) {
    throw invalid('returns/diagnostics')
  }
  const inKind = diagnostics.unclassifiedInKindFlows
  if (
    !isRecord(inKind) ||
    typeof inKind.present !== 'boolean' ||
    typeof inKind.count !== 'number' ||
    !Number.isInteger(inKind.count) ||
    inKind.count < 0 ||
    (inKind.signedFmv !== undefined && !isDecimalString(inKind.signedFmv))
  ) {
    throw invalid('unclassifiedInKindFlows')
  }
  if (!Array.isArray(diagnostics.notes) || !diagnostics.notes.every((note) => typeof note === 'string')) {
    throw invalid('notes')
  }
  const amountField = (name: string): StatementAmount => {
    const source = name.split('.').reduce<unknown>(
      (node, key) => (isRecord(node) ? node[key] : undefined),
      value,
    )
    return decodeAmount(source, name)
  }
  return {
    version: 2,
    kind: 'statement',
    context: {
      accountSelection,
      accountIds: accountIds as number[],
      effectiveDate: context.effectiveDate,
      currency: context.currency,
      digits: context.digits,
    },
    status: value.status,
    reasons: value.reasons as string[],
    capital: {
      invested: amountField('capital.invested'),
      cashOut: amountField('capital.cashOut'),
      netInvestedCapital: amountField('capital.netInvestedCapital'),
    },
    netResult: {
      nav: amountField('netResult.nav'),
      controlTotal: amountField('netResult.controlTotal'),
      components: {
        realizedPrice: amountField('netResult.components.realizedPrice'),
        unrealizedPrice: amountField('netResult.components.unrealizedPrice'),
        income: amountField('netResult.components.income'),
        fees: amountField('netResult.components.fees'),
        taxes: amountField('netResult.components.taxes'),
        fx: amountField('netResult.components.fx'),
        otherFlows: amountField('netResult.components.otherFlows'),
      },
      fxDetail: {
        security: amountField('netResult.fxDetail.security'),
        cashFlows: amountField('netResult.fxDetail.cashFlows'),
      },
      attributedSum: amountField('netResult.attributedSum'),
      unexplainedDifference: amountField('netResult.unexplainedDifference'),
      toleranceRaw: netResult.toleranceRaw,
      toleranceBasis: netResult.toleranceBasis,
      reconciliation: netResult.reconciliation,
    },
    returns: {
      totalReturn: decodeReturn(returns.totalReturn, 'returns.totalReturn'),
      irr: decodeReturn(returns.irr, 'returns.irr'),
    },
    diagnostics: {
      omittedValuations: diagnostics.omittedValuations as Record<string, unknown>[],
      unclassifiedInKindFlows: inKind as ReconciledStatement['diagnostics']['unclassifiedInKindFlows'],
      notes: diagnostics.notes as string[],
    },
  }
}

function assertResponseContext(
  expected: CapturedSummaryContext,
  context: StatementContext,
): void {
  // The established context conventions (chart contract): selection identity,
  // reporting currency and digits must match the captured request; the
  // statement binds its date to the committed effective date (there is no
  // separate date range on this endpoint).
  const selection = context.accountSelection
  if (
    selection.type !== expected.accountSelection.type ||
    selection.id !== expected.accountSelection.id
  ) {
    throw new SummaryContextMismatchError(
      'Statement response account selection does not match the committed selection',
    )
  }
  if (context.effectiveDate !== expected.effectiveCurrentDate) {
    throw new SummaryContextMismatchError(
      `Statement response effective date ${context.effectiveDate} does not match the committed date ${expected.effectiveCurrentDate}`,
    )
  }
  if (context.currency !== expected.currency) {
    throw new SummaryContextMismatchError(
      `Statement response currency ${context.currency} does not match the committed currency ${expected.currency}`,
    )
  }
  if (context.digits !== expected.digits) {
    throw new SummaryContextMismatchError(
      `Statement response digits ${context.digits} do not match the committed digits ${expected.digits}`,
    )
  }
}

export async function getDashboardSummaryV2(
  captured: CapturedSummaryContext,
  options?: RequestOptions,
): Promise<DashboardSummaryResult> {
  const candidate = captured as unknown as Record<string, unknown> | undefined
  if (
    !isRecord(candidate) ||
    !isRecord(candidate.accountSelection) ||
    typeof candidate.effectiveCurrentDate !== 'string' ||
    typeof candidate.currency !== 'string' ||
    typeof candidate.digits !== 'number'
  ) {
    throw new ApiError('Dashboard summary requires the captured portfolio context')
  }
  const value = await apiGet('/dashboard/api/get-summary/?summary_contract=2', options)
  const legacy = decodeDashboardSummary(value)
  if (!isRecord(value) || !('summaryV2' in value)) {
    return { capability: 'legacy_only', legacy }
  }
  // Present-but-invalid v2 must error here, never a silent downgrade.
  const statement = decodeStatement(value.summaryV2)
  assertResponseContext(captured, statement.context)
  return { capability: 'v2', legacy, statement }
}
