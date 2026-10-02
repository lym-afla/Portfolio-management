// Opt-in chart contract v2 NAV transport (C2). Uses the shared injected
// Axios instance (preserving its auth interceptors) with an explicit
// chart_contract=2 negotiation: a v2 response is validated, an HTTP 200
// without chartV2 is honest legacy_only, and any other failure is a typed
// local error — never a silent downgrade or a second legacy request. The
// transport performs no state changes or context reconciliation.
import type { AxiosRequestConfig } from 'axios'
import { getApiTransport } from '@/services/http/client'
import { toApiError } from '@/services/http/errors'
import type { ChartDocument, NavQuery, NavResult } from './contracts'
import { parseNavEnvelope } from './parseChartEnvelope'

const NAV_CHART_ENDPOINT = '/dashboard/api/get-nav-chart-data/'

/** A C1 chart error or a locally sanitized transport failure. */
export class ChartApiError extends Error {
  readonly status?: number
  readonly code?: string
  readonly retryable: boolean

  constructor(message: string, status: number | undefined, code: string | undefined, retryable: boolean) {
    super(message)
    this.name = 'ChartApiError'
    this.status = status
    this.code = code
    this.retryable = retryable
  }
}

/** The response disagrees with the captured request context. */
export class ChartContextMismatchError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ChartContextMismatchError'
    this.status = status
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
  if (!sameSelection(query.context.accountSelection, context.accountSelection)) {
    throw new ChartContextMismatchError('Chart response account selection does not match the committed selection')
  }
  if (context.currency !== query.context.currency) {
    throw new ChartContextMismatchError(
      `Chart response currency ${context.currency} does not match the committed currency ${query.context.currency}`
    )
  }
  if (context.digits !== query.context.digits) {
    throw new ChartContextMismatchError(
      `Chart response digits ${context.digits} do not match the committed digits ${query.context.digits}`
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
