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
export async function getDashboardSummary(options?: RequestOptions): Promise<DashboardSummary> {
  return decodeDashboardSummary(await apiGet('/dashboard/api/get-summary/', options))
}
