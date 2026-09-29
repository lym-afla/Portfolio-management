import { ApiError } from '@/services/http/errors'
import type { AccountSelection, PortfolioContext } from '@/types/portfolioContext'
import { apiGet, apiPost } from '@/services/http/client'
import { isRecord } from '@/types/portfolioTables'

export type ContextValues = Omit<PortfolioContext, 'revision'>
export interface PortfolioContextBackend {
  read(): Promise<ContextValues>
  updateAccount(selection: AccountSelection): Promise<void>
  updateSettings(settings: {
    effectiveCurrentDate: string; currency: string; digits: number
  }): Promise<void>
}
export type EffectiveDateRefresh = (date: string) => Promise<unknown>
let installedBackend: PortfolioContextBackend | null = null
export function configurePortfolioContextBackend(backend: PortfolioContextBackend | null): void {
  installedBackend = backend
}
export function getPortfolioContextBackend(): PortfolioContextBackend {
  if (!installedBackend) throw new Error('Portfolio context backend is not initialized')
  return installedBackend
}
function selectionFrom(value: unknown): AccountSelection {
  if (!isRecord(value)) throw new ApiError('Invalid account selection response')
  const type = 'selected_account_type' in value ? value.selected_account_type : value.type
  const id = 'selected_account_id' in value ? value.selected_account_id : value.id
  if (type === 'all' && id === null) return { type, id: null }
  if ((type === 'account' || type === 'broker' || type === 'group') && Number.isInteger(id) && (id as number) > 0) {
    return { type, id: id as number }
  }
  throw new ApiError('Invalid account selection response')
}
// A 4xx from the mutation POST is distinct from a later readback/refresh failure.
// The store can retain known committed values only for this explicit rejection.
async function postContextMutation(url: string, body: unknown): Promise<unknown> {
  try { return await apiPost(url, body) }
  catch (error) {
    if (error instanceof ApiError && [400, 403, 404, 422].includes(error.status || 0)) {
      throw new ApiError(error.message, error.status, 'context_mutation_rejected', error.details)
    }
    throw error
  }
}
export function createPortfolioContextBackend(refreshTokenWithEffectiveDate: EffectiveDateRefresh): PortfolioContextBackend {
  const backend: PortfolioContextBackend = {
    async read(): Promise<ContextValues> {
      const [userSettings, dashboard] = await Promise.all([
        apiGet('/users/api/user_settings/'),
        apiGet('/users/api/dashboard_settings/'),
      ])
      if (!isRecord(dashboard) || !isRecord(dashboard.settings)) {
        throw new ApiError('Invalid dashboard settings response')
      }
      const settings = dashboard.settings
      if ((typeof settings.table_date !== 'string' && settings.table_date !== null) ||
          typeof settings.default_currency !== 'string' ||
          !Number.isInteger(settings.digits)) {
        throw new ApiError('Invalid dashboard settings response')
      }
      return {
        accountSelection: selectionFrom(userSettings),
        effectiveCurrentDate: settings.table_date as string | null,
        currency: settings.default_currency,
        digits: settings.digits as number,
      }
    },
    async updateAccount(selection: AccountSelection): Promise<void> {
      const response = await postContextMutation('/users/api/update_user_data_for_new_account/',
        { type: selection.type, id: selection.id })
      if (!isRecord(response) || response.success !== true || !isRecord(response.selected)) {
        throw new ApiError('Invalid account update response')
      }
      const confirmed = selectionFrom(response.selected)
      if (confirmed.type !== selection.type || confirmed.id !== selection.id) {
        throw new ApiError('Account selection was not confirmed')
      }
      await backend.read()
    },
    async updateSettings(settings): Promise<void> {
      const response = await postContextMutation('/users/api/update_dashboard_settings/', {
        table_date: settings.effectiveCurrentDate,
        default_currency: settings.currency,
        digits: settings.digits,
      })
      if (!isRecord(response) ||
          response.table_date !== settings.effectiveCurrentDate ||
          response.default_currency !== settings.currency ||
          response.digits !== settings.digits ||
          (response.requires_token_refresh !== undefined && typeof response.requires_token_refresh !== 'boolean') ||
          (response.new_effective_date !== undefined && response.new_effective_date !== settings.effectiveCurrentDate) ||
          (response.requires_token_refresh === true && response.new_effective_date !== settings.effectiveCurrentDate)) {
        throw new ApiError('Invalid dashboard settings update response')
      }
      if (response.requires_token_refresh === true) {
        await refreshTokenWithEffectiveDate(settings.effectiveCurrentDate)
      }
      const confirmed = await backend.read()
      if (confirmed.effectiveCurrentDate !== settings.effectiveCurrentDate ||
          confirmed.currency !== settings.currency ||
          confirmed.digits !== settings.digits) {
        throw new ApiError('Dashboard settings were not confirmed')
      }
    },
  }
  return backend
}
