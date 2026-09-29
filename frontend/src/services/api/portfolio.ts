import { apiPost, type RequestOptions } from '@/services/http/client'
import { ApiError } from '@/services/http/errors'
import { decodePage, isRecord, type SortBy, type OpenPositionsResponse, type ClosedPositionsResponse } from '@/types/portfolioTables'

export function decodeOpenPositions(value: unknown): OpenPositionsResponse {
  const page = decodePage(value, 'open positions', 'portfolio_open')
  if (!isRecord(page.portfolio_open_totals) || !isRecord(page.cash_balances) ||
      !(page.portfolio_open as unknown[]).every((row) => isRecord(row) && typeof row.name === 'string' && typeof row.type === 'string')) {
    throw new ApiError('Invalid open positions response')
  }
  return page as unknown as OpenPositionsResponse
}
export function decodeClosedPositions(value: unknown): ClosedPositionsResponse {
  const page = decodePage(value, 'closed positions', 'portfolio_closed')
  if (!isRecord(page.portfolio_closed_totals) || page.cash_balances !== null ||
      !(page.portfolio_closed as unknown[]).every((row) => isRecord(row) && typeof row.name === 'string' && typeof row.type === 'string')) {
    throw new ApiError('Invalid closed positions response')
  }
  return page as unknown as ClosedPositionsResponse
}
export async function getOpenPositions(
  dateFrom: string | null, dateTo: string | null, page: number, itemsPerPage: number,
  search = '', sortBy: SortBy = {}, options?: RequestOptions,
): Promise<OpenPositionsResponse> {
  return decodeOpenPositions(await apiPost('/open_positions/api/get_open_positions_table/',
    { dateFrom, dateTo, page, itemsPerPage, search, sortBy }, options))
}
export async function getClosedPositions(
  dateFrom: string | null, dateTo: string | null, page: number, itemsPerPage: number,
  search = '', sortBy: SortBy = {}, options?: RequestOptions,
): Promise<ClosedPositionsResponse> {
  return decodeClosedPositions(await apiPost('/closed_positions/api/get_closed_positions_table/',
    { dateFrom, dateTo, page, itemsPerPage, search, sortBy }, options))
}
