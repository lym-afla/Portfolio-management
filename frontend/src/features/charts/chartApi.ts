// Opt-in chart contract v2 transport (C2 NAV; C4 breakdown + security
// histories). Uses the shared injected Axios instance (preserving its auth
// interceptors) with an explicit chart_contract=2 negotiation: a v2 response
// is validated, an HTTP 200 without chartV2 is honest legacy_only, and any
// other failure is a typed local error — never a silent downgrade or a second
// legacy request. The transport performs no state changes or context
// reconciliation.
import type { AxiosRequestConfig } from 'axios'
import { getApiTransport } from '@/services/http/client'
import { ApiError, toApiError } from '@/services/http/errors'
import type {
  AllocationResult,
  BreakdownQuery,
  ChartDocument,
  LegacyBreakdown,
  LegacySecurityHistory,
  NavQuery,
  NavResult,
  ReadyChartContext,
  SecurityHistoryQuery,
  SecurityHistoryResult,
} from './contracts'
import { parseAllocationEnvelope, parseNavEnvelope, parseSecurityEnvelope } from './parseChartEnvelope'

const NAV_CHART_ENDPOINT = '/dashboard/api/get-nav-chart-data/'
const BREAKDOWN_ENDPOINT = '/dashboard/api/get-breakdown/'

// Extending ApiError keeps the shared sanitizing constructor in the path for
// every message and code this boundary emits, including nested C1 envelopes.
/** A C1 chart error or a locally sanitized transport failure. */
export class ChartApiError extends ApiError {
  readonly retryable: boolean

  constructor(message: string, status?: number, code?: string, retryable = false) {
    super(message, status, code)
    this.name = 'ChartApiError'
    this.retryable = retryable
  }
}

/** The response disagrees with the captured request context. */
export class ChartContextMismatchError extends ApiError {
  constructor(message: string, status?: number) {
    super(message, status)
    this.name = 'ChartContextMismatchError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function toChartApiError(error: unknown): ChartApiError {
  const base = toApiError(error)
  // Prefer the C1 nested error envelope; a body that does not match it is a
  // local failure that can never be certified retryable.
  const body = isRecord(error) && isRecord(error.response) ? error.response.data : undefined
  const chartError = isRecord(body) ? body.error : undefined
  if (
    isRecord(chartError) &&
    typeof chartError.code === 'string' &&
    typeof chartError.message === 'string' &&
    typeof chartError.retryable === 'boolean'
  ) {
    return new ChartApiError(chartError.message, base.status, chartError.code, chartError.retryable)
  }
  return new ChartApiError(base.message, base.status, undefined, false)
}

function sameSelection(
  left: NavQuery['context']['accountSelection'],
  right: unknown,
): boolean {
  if (!isRecord(right)) return false
  return left.type === right.type && left.id === right.id
}

function assertResponseContext(query: Readonly<NavQuery>, document: ChartDocument): void {
  const context = document.context
  // The backend binds effectiveDate to the chart's dateTo (historical ranges
  // are valid); the committed effective date still owns readiness elsewhere.
  if (context.effectiveDate !== query.toDate) {
    throw new ChartContextMismatchError(
      `Chart response effective date ${context.effectiveDate} does not match the requested end date ${query.toDate}`
    )
  }
  assertContextIdentity(query.context, context)
}

/**
 * The shared selection/currency/digits check. Each endpoint binds the
 * document date to its own semantics: NAV answers `toDate`; the breakdown and
 * the security histories have no explicit end date, so their documents answer
 * the request's committed effective date (see fetchBreakdownChart /
 * fetchSecurityHistory).
 */
function assertContextIdentity(expected: ReadyChartContext, context: ChartDocument['context']): void {
  if (!sameSelection(expected.accountSelection, context.accountSelection)) {
    throw new ChartContextMismatchError('Chart response account selection does not match the committed selection')
  }
  if (context.currency !== expected.currency) {
    throw new ChartContextMismatchError(
      `Chart response currency ${context.currency} does not match the committed currency ${expected.currency}`
    )
  }
  if (context.digits !== expected.digits) {
    throw new ChartContextMismatchError(
      `Chart response digits ${context.digits} do not match the committed digits ${expected.digits}`
    )
  }
  // accountIds are validated for shape by the document parser; the client
  // cannot reconstruct broker/group membership, so no list comparison here.
}

function isAbort(error: unknown): boolean {
  return (
    isRecord(error) &&
    (error.name === 'CanceledError' ||
      error.name === 'AbortError' ||
      error.code === 'ERR_CANCELED' ||
      error.code === 'ECONNABORTED')
  )
}

/** Fetch the NAV chart with explicit v2 negotiation; exactly one request. */
export async function fetchNavChart(
  query: Readonly<NavQuery>,
  options: { signal: AbortSignal },
): Promise<NavResult> {
  const config: AxiosRequestConfig & { params: Record<string, string | number | null> } = {
    signal: options.signal,
    params: {
      chart_contract: 2,
      breakdown: query.mode,
      frequency: query.frequency,
      dateFrom: query.fromDate,
      dateTo: query.toDate,
    },
  }
  let data: unknown
  try {
    data = (await getApiTransport().get(NAV_CHART_ENDPOINT, config)).data
  } catch (error) {
    if (isAbort(error)) throw error
    throw toChartApiError(error)
  }
  const result = parseNavEnvelope(data)
  if (result.capability === 'v2') assertResponseContext(query, result.document)
  return result
}

/** The committed effective date both new endpoints answer with (no dateTo). */
function assertSecurityDate(expected: ReadyChartContext, document: ChartDocument): void {
  if (document.context.effectiveDate !== expected.effectiveCurrentDate) {
    throw new ChartContextMismatchError(
      `Chart response effective date ${document.context.effectiveDate} does not match the committed effective date ${expected.effectiveCurrentDate}`
    )
  }
}

/**
 * The dashboard breakdown with explicit v2 negotiation: ONE request carrying
 * all three allocation documents beside the legacy card fields. The documents
 * answer the request's committed effective date (the endpoint has no date
 * parameter), never a NAV-style toDate.
 */
export async function fetchBreakdownChart(
  query: Readonly<BreakdownQuery>,
  options: { signal: AbortSignal },
): Promise<AllocationResult> {
  const config: AxiosRequestConfig & { params: Record<string, number> } = {
    signal: options.signal,
    params: { chart_contract: 2 },
  }
  let data: unknown
  try {
    data = (await getApiTransport().get(BREAKDOWN_ENDPOINT, config)).data
  } catch (error) {
    if (isAbort(error)) throw error
    throw toChartApiError(error)
  }
  const result = parseAllocationEnvelope(data)
  if (result.capability === 'v2') {
    for (const document of [result.documents.assetType, result.documents.assetClass, result.documents.currency]) {
      if (document.context.effectiveDate !== query.context.effectiveCurrentDate) {
        throw new ChartContextMismatchError(
          `Breakdown response effective date ${document.context.effectiveDate} does not match the committed effective date ${query.context.effectiveCurrentDate}`
        )
      }
      assertContextIdentity(query.context, document.context)
    }
  }
  return result
}

/**
 * One security history (price or position) with explicit v2 negotiation.
 * The price endpoint has no account parameter at all — the local filter is
 * sent for position only. The document must answer the requested security
 * identity and the committed effective date; instrument currencies (price
 * axis) are the security's own and are never compared against the reporting
 * currency. Exactly one request; a missing v2 field is legacy_only.
 */
export async function fetchSecurityHistory(
  query: Readonly<SecurityHistoryQuery>,
  kind: 'price' | 'position',
  options: { signal: AbortSignal },
): Promise<SecurityHistoryResult> {
  const params: Record<string, string | number> = { chart_contract: 2, period: query.period }
  if (kind === 'position' && query.accountId !== null) params.account_id = query.accountId
  const config: AxiosRequestConfig & { params: Record<string, string | number> } = {
    signal: options.signal,
    params,
  }
  const endpoint = `/database/api/securities/${query.securityId}/${kind}-history/`
  let data: unknown
  try {
    data = (await getApiTransport().get(endpoint, config)).data
  } catch (error) {
    if (isAbort(error)) throw error
    throw toChartApiError(error)
  }
  const result = parseSecurityEnvelope(data, kind)
  if (result.capability === 'v2') {
    if (result.document.security?.id !== query.securityId) {
      throw new ChartContextMismatchError(
        `Security ${kind} document answers security ${String(result.document.security?.id)} instead of ${query.securityId}`
      )
    }
    assertSecurityDate(query.context, result.document)
    assertContextIdentity(query.context, result.document.context)
  }
  return result
}

/** Exported for consumers that narrow the legacy breakdown payload shape. */
export type { LegacyBreakdown, LegacySecurityHistory }
