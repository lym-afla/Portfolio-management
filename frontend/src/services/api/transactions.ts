import { ApiError } from '@/services/http/errors'
import { apiPost, type RequestOptions } from '@/services/http/client'
import { decodePage, isRecord, type SortBy, type TransactionsResponse } from '@/types/portfolioTables'

export function decodeTransactions(value: unknown): TransactionsResponse {
  const page = decodePage(value, 'transactions', 'transactions')
  if (!Array.isArray(page.currencies) || !page.currencies.every((currency) => typeof currency === 'string') ||
      !(page.transactions as unknown[]).every((row) => isRecord(row) &&
        typeof row.id === 'string' && typeof row.transaction_type === 'string' &&
        typeof row.date === 'string' && typeof row.type === 'string')) {
    throw new ApiError('Invalid transactions response')
  }
  return page as unknown as TransactionsResponse
}
export async function getTransactions(
  dateFrom: string | null, dateTo: string | null, page: number, itemsPerPage: number,
  search = '', sortBy: SortBy = {}, options?: RequestOptions,
): Promise<TransactionsResponse> {
  return decodeTransactions(await apiPost('/transactions/api/get_transactions_table/',
    { page, itemsPerPage, search, dateFrom, dateTo, sortBy }, options))
}
