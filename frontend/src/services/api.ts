import axiosInstance from '@/config/axiosConfig'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import logger from '@/utils/logger'
import type { components } from '@/types/api'

// Schema aliases sourced from the generated OpenAPI types.
type Account = components['schemas']['Account']
type AccountGroup = components['schemas']['AccountGroup']
type Broker = components['schemas']['Broker']
type FX = components['schemas']['FX']
type TransactionForm = components['schemas']['TransactionForm']
type FXTransactionForm = components['schemas']['FXTransactionForm']
type DashboardSummaryResponse = components['schemas']['DashboardSummaryResponse']
type User = components['schemas']['User']

// The /users/api/profile/ endpoint returns the User schema plus extra
// account-selection preference fields that aren't captured by the
// generated OpenAPI schema.
type UserProfile = User & {
  selected_account_type?: string | null
  selected_account_id?: number | null
  [key: string]: unknown
}

// The backend serves several function-based-view endpoints that return
// untyped dicts. These aliases keep the signatures readable while staying
// honest about the fact that their shapes aren't in the OpenAPI spec.
type ApiRecord = Record<string, unknown>

// Sort descriptor shape used by the data-table endpoints (open/closed
// positions, transactions, prices, FX). The backend accepts a single sort
// object or an empty object.
interface SortBy {
  key?: string
  order?: 'asc' | 'desc'
  [key: string]: unknown
}

// Login response shape (JWT tokens + user info). The login FBV is not
// described in the OpenAPI spec, but it is one of the most-used functions
// so we type it explicitly.
interface LoginResponse {
  access?: string
  refresh?: string
  user?: User
  effective_current_date?: string
  [key: string]: unknown
}

// Paginated table response used by open/closed positions and transactions.
interface PaginatedTableResponse {
  count?: number
  page?: number
  num_pages?: number
  [key: string]: unknown
}

export const login = async (username: string, password: string): Promise<LoginResponse> => {
  try {
    const response = await axiosInstance.post('/users/api/login/', {
      username,
      password,
    })
    logger.log('Unknown', 'Response from login:', response)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const refreshToken = async (): Promise<{ access?: string; refresh?: string; effective_current_date?: string }> => {
  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) {
    throw new Error('No refresh token available')
  }

  try {
    const response = await axiosInstance.post('/users/api/refresh-token/', {
      refresh: refreshToken,
    })
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error refreshing token:', error)
    throw error
  }
}

export const register = async (username: string, email: string, password: string, password2: string): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post('/users/api/register/', {
      username,
      email,
      password,
      password2,
    })
    logger.log('Unknown', 'Registration response:', response)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Registration error:', error.response)
    if (error.response && error.response.data && error.response.data.errors) {
      throw error.response.data.errors
    } else {
      throw { general: ['An unexpected error occurred. Please try again.'] }
    }
  }
}

export const getAccountChoices = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/users/api/get_account_choices/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateUserDataForNewAccount = async (selection: { type: string; id: number }): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/update_user_data_for_new_account/',
      {
        type: selection.type,
        id: selection.id,
      }
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getUserProfile = async (): Promise<UserProfile> => {
  try {
    const response = await axiosInstance.get('/users/api/profile/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const editUserProfile = async (profileData: Partial<UserProfile>): Promise<{ success: boolean; errors?: ApiRecord }> => {
  try {
    const response = await axiosInstance.put(
      '/users/api/edit_profile/',
      profileData
    )
    return response.data
  } catch (error) {
    return {
      success: false,
      errors: error.response?.data || { general: [error.message] },
    }
  }
}

export const changePassword = async (passwordData: { old_password?: string; new_password?: string; [key: string]: unknown }): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/change_password/',
      passwordData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getUserSettings = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/users/api/user_settings/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateUserSettings = async (settings: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/user_settings/',
      settings
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSettingsChoices = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/users/api/user_settings_choices/'
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const logout = async (): Promise<ApiRecord> => {
  try {
    const refreshToken = localStorage.getItem('refreshToken')
    if (!refreshToken) {
      throw new Error('No refresh token found')
    }
    const response = await axiosInstance.post('/users/api/logout/', {
      refresh_token: refreshToken,
    })

    // Clear all authentication tokens
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')

    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error during logout:', error)
    // Even if the server request fails, we should clear local tokens
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    throw error.response ? error.response.data : error.message
  }
}

export const deleteUserAccount = async (): Promise<ApiRecord> => {
  try {
    const refreshToken = localStorage.getItem('refreshToken')
    const response = await axiosInstance.delete('/users/api/delete_account/', {
      data: { refresh_token: refreshToken },
    })
    // Clear all authentication tokens
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error deleting account:', error.response || error)
    throw error.response ? error.response.data : error.message
  }
}

export const getDashboardSettings = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/users/api/dashboard_settings/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching dashboard settings:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateDashboardSettings = async (settings: ApiRecord): Promise<{ success: boolean; error?: ApiRecord; requires_token_refresh?: boolean; new_effective_date?: string; [key: string]: unknown }> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/update_dashboard_settings/',
      settings
    )

    // Check if token refresh is required (effective_date changed)
    if (
      response.data.requires_token_refresh &&
      response.data.new_effective_date
    ) {
      logger.log(
        'Unknown',
        `Effective date changed to ${response.data.new_effective_date}, refreshing JWT token...`
      )

      // Import the refresh function from axiosConfig
      const { refreshTokenWithEffectiveDate } = await import(
        '@/config/axiosConfig'
      )

      try {
        // eslint-disable-next-line no-unused-vars
        const newToken = await refreshTokenWithEffectiveDate(
          response.data.new_effective_date
        )
        logger.log(
          'Unknown',
          `JWT token refreshed with new effective_date: ${response.data.new_effective_date}`
        )

        // Force update the auth store immediately with the refreshed tokens.
        try {
          const authStore = useAuthStore()
          const accessToken = localStorage.getItem('accessToken')
          const refreshToken = localStorage.getItem('refreshToken')
          authStore.setTokens({
            accessToken: accessToken,
            refreshToken: refreshToken,
          })
          logger.log('Unknown', 'Auth store updated with new tokens')
        } catch (e) {
          logger.warn('Unknown', 'Could not sync tokens to auth store:', e)
        }

        // Small delay to ensure token propagation
        await new Promise((resolve) => setTimeout(resolve, 50))

        logger.log('Unknown', 'Token refresh and store update complete')
      } catch (refreshError) {
        logger.error('Unknown', 'Failed to refresh JWT token:', refreshError)
        // Don't fail the whole operation if refresh fails, just log it
      }
    }

    return { success: true, ...response.data }
  } catch (error) {
    logger.error('Unknown', 'Error updating dashboard settings:', error)
    return {
      success: false,
      error: error.response ? error.response.data : error.message,
    }
  }
}

export const getEffectiveCurrentDate = async (): Promise<{ date?: string; effective_current_date?: string; [key: string]: unknown }> => {
  const response = await axiosInstance.get('/api/effective-current-date/')
  return response.data
}

export const getAssetTypes = async (): Promise<ApiRecord | ApiRecord[]> => {
  try {
    const response = await axiosInstance.get('/database/api/get-asset-types/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getOpenPositions = async (
  dateFrom: string,
  dateTo: string,
  page: number,
  itemsPerPage: number,
  search = '',
  sortBy: SortBy = {}
): Promise<PaginatedTableResponse> => {
  console.log('[api.js] getOpenPositions called with:', {
    dateFrom,
    dateTo,
    page,
    itemsPerPage,
    search,
    sortBy,
  })
  try {
    const response = await axiosInstance.post(
      '/open_positions/api/get_open_positions_table/',
      {
        dateFrom,
        dateTo,
        page,
        itemsPerPage,
        search,
        sortBy,
      }
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching open positions:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getClosedPositions = async (
  dateFrom: string,
  dateTo: string,
  page: number,
  itemsPerPage: number,
  search = '',
  sortBy: SortBy = {}
): Promise<{ portfolio_closed?: ApiRecord[]; [key: string]: unknown }> => {
  try {
    const response = await axiosInstance.post(
      '/closed_positions/api/get_closed_positions_table/',
      {
        dateFrom,
        dateTo,
        page,
        itemsPerPage,
        search,
        sortBy, // This will be a single object or an empty object
      }
    )
    console.log('API request payload:', {
      dateFrom,
      dateTo,
      page,
      itemsPerPage,
      search,
      sortBy,
    })
    logger.log('Unknown', 'API response:', response.data)
    if (
      response.data &&
      response.data.portfolio_closed &&
      Array.isArray(response.data.portfolio_closed)
    ) {
      return response.data
    } else {
      logger.error('Unknown', 'Unexpected response format:', response.data)
      throw new Error('Invalid response format')
    }
  } catch (error) {
    logger.error('Unknown', 'Error fetching closed positions:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getYearOptions = async (): Promise<number[]> => {
  try {
    const response = await axiosInstance.get('/api/get-year-options/')
    return response.data.table_years
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurities = async (assetTypes: string[] = [], accountId: number | null = null): Promise<ApiRecord[]> => {
  try {
    const params = new URLSearchParams()
    if (assetTypes.length > 0) {
      params.append('asset_types', assetTypes.join(','))
    }
    if (accountId) {
      params.append('account_id', String(accountId))
    }
    const response = await axiosInstance.get('/database/api/get-securities/', {
      params,
    })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPrices = async (params: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/get-prices-table/',
      params
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching prices:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getSecuritiesForDatabase = async (params: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/get-securities-for-database/',
      params
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export interface SecurityFieldDiffEntry {
  existing: unknown
  submitted: unknown
}

export interface SecurityConflictPayload {
  success: false
  conflict: true
  existing_asset: {
    id: number
    name: string
    ISIN: string
    currency: string
  }
  field_diff: Record<string, SecurityFieldDiffEntry>
  fillable: string[]
}

export function isSecurityConflictPayload(
  data: unknown
): data is SecurityConflictPayload {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as Record<string, unknown>).conflict === true
  )
}

export const createSecurity = async (securityData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/create-security/',
      securityData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityDetail = async (securityId: number, accountId: number | null = null): Promise<ApiRecord> => {
  try {
    const params: Record<string, number> = {}
    if (accountId) params.account_id = accountId
    const response = await axiosInstance.get(
      `/database/api/securities/${securityId}/`,
      { params }
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching security detail:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityPriceHistory = async (securityId: number, period: string): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      `/database/api/securities/${securityId}/price-history/`,
      {
        params: { period },
      }
    )
    logger.log('Unknown', '[api.js] Security price history:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching security price history:', error)
    throw error
  }
}

export const getSecurityPositionHistory = async (securityId: number, period: string, accountId: number | null = null): Promise<ApiRecord> => {
  try {
    const params: Record<string, string | number> = { period }
    if (accountId) params.account_id = accountId
    const response = await axiosInstance.get(
      `/database/api/securities/${securityId}/position-history/`,
      { params }
    )
    logger.log('Unknown', '[api.js] Security position history:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching security position history:', error)
    throw error
  }
}

export const getSecurityTransactions = async (securityId: number, options: { page: number; itemsPerPage: number }, period: string, accountId: number | null = null): Promise<ApiRecord> => {
  try {
    const { page, itemsPerPage } = options
    const params: Record<string, number | string> = {
      page,
      itemsPerPage,
      period,
    }
    if (accountId) params.account_id = accountId
    const response = await axiosInstance.get(
      `/database/api/securities/${securityId}/transactions/`,
      { params }
    )
    logger.log('Unknown', '[api.js] Security transactions:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching security transactions:', error)
    throw error
  }
}

export const updateSecurity = async (securityId: number, securityData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.put(
      `/database/api/update-security/${securityId}/`,
      securityData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteSecurity = async (securityId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(
      `/database/api/delete-security/${securityId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getDashboardBreakdown = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/dashboard/api/get-breakdown/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching breakdown data:', error)
    throw error
  }
}

export const getDashboardSummaryOverTime = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/dashboard/api/get-summary-over-time/'
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching summary over time data:', error)
    throw error
  }
}

export const getNAVChartData = async (
  breakdown: string,
  frequency: string,
  dateFrom: string,
  dateTo: string
): Promise<ApiRecord> => {
  try {
    console.log('API request params for NAV chart:', {
      breakdown: breakdown,
      frequency: frequency,
      dateFrom: dateFrom,
      dateTo: dateTo,
    })
    const response = await axiosInstance.get(
      '/dashboard/api/get-nav-chart-data/',
      {
        params: {
          breakdown,
          frequency,
          dateFrom,
          dateTo,
        },
      }
    )
    logger.log('Unknown', 'API response:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching NAV chart data:', error)
    throw error
  }
}

export const getDashboardSummary = async (): Promise<DashboardSummaryResponse> => {
  try {
    const response = await axiosInstance.get('/dashboard/api/get-summary/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching dashboard summary:', error)
    throw error
  }
}

export const getAccountPerformanceFormData = async (): Promise<ApiRecord> => {
  const response = await axiosInstance.get(
    '/database/api/update-account-performance/'
  )
  return response.data
}

export const updateAccountPerformance = async (formData: ApiRecord): Promise<{ status: string; message?: string; [key: string]: unknown }> => {
  try {
    const effectiveCurrentDate = useAppStore().effectiveCurrentDate
    if (!effectiveCurrentDate) {
      throw new Error('Effective current date not set')
    }

    const dataToSend = {
      ...formData,
      effective_current_date: effectiveCurrentDate,
    }

    // Start the update process
    const startResponse = await axiosInstance.post(
      '/database/api/update-account-performance/start/',
      dataToSend
    )

    const sessionId = startResponse.data.session_id

    const token = localStorage.getItem('accessToken')
    if (!token) {
      throw new Error('No authentication token available')
    }

    // Create EventSource with both session ID and token
    const source = new EventSource(
      `${import.meta.env.VITE_API_URL}/database/api/update-account-performance/sse/?session_id=${sessionId}&token=${token}`,
      {
        withCredentials: false,
      }
    )

    return new Promise((resolve, reject) => {
      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          logger.log('Unknown', '[api.js] SSE message received:', data)

          if (data.status === 'error' && data.type === 'authentication') {
            source.close()
            reject(new Error('Authentication failed'))
            return
          }

          window.dispatchEvent(
            new CustomEvent('accountPerformanceUpdateProgress', {
              detail: data,
            })
          )

          if (data.status === 'complete') {
            source.close()
            resolve(data)
          } else if (data.status === 'error') {
            source.close()
            reject(new Error(data.message))
          }
        } catch (error) {
          logger.error('Unknown', 'Error parsing SSE message:', error)
          source.close()
          reject(error)
        }
      }

      source.onerror = (error) => {
        logger.error('Unknown', 'SSE connection error:', error)
        source.close()
        reject(new Error('SSE connection failed'))
      }

      // Handle authentication errors
      source.addEventListener('error', (event) => {
        const target = event.target as unknown as EventSource
        if (target.readyState === EventSource.CLOSED) {
          logger.error('Unknown', 'SSE connection closed due to error')
          reject(new Error('Connection closed due to error'))
        }
      })
    })
  } catch (error) {
    logger.error('Unknown', 'Error updating account performance:', error)
    window.dispatchEvent(
      new CustomEvent('accountPerformanceUpdateError', {
        detail: { message: error.message || 'Unknown error occurred' },
      })
    )
    throw error
  }
}

export const addPrice = async (priceData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/add-price/',
      priceData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deletePrice = async (priceId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(
      `/database/api/delete-price/${priceId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPriceDetails = async (priceId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      `/database/api/get-price-details/${priceId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updatePrice = async (priceId: number, priceData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.put(
      `/database/api/update-price/${priceId}/`,
      priceData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/database/api/security-form-structure/'
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityDetails = async (id: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      `/database/api/get-security-details/${id}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPriceImportFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/database/api/price-import/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const createMerger = async ({
  oldSecurityId,
  newSecurityId,
  mergerDate,
  conversionRatio,
  cashPerShare,
}: {
  oldSecurityId: number
  newSecurityId?: number | null
  mergerDate: string
  conversionRatio?: number | string | null
  cashPerShare?: number | string | null
}): Promise<ApiRecord> => {
  try {
    const data: Record<string, unknown> = {
      old_security_id: oldSecurityId,
      merger_date: mergerDate,
    }
    if (newSecurityId) data.new_security_id = newSecurityId
    if (conversionRatio) data.conversion_ratio = conversionRatio
    if (cashPerShare) data.cash_per_share = cashPerShare

    const response = await axiosInstance.post('/database/api/create-merger/', data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error creating merger:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const importPrices = async (importData: ApiRecord): Promise<string | ApiRecord> => {
  try {
    const effectiveCurrentDate = useAppStore().effectiveCurrentDate
    if (!effectiveCurrentDate) {
      throw new Error('Effective current date not set')
    }

    const dataToSend = {
      ...importData,
      effective_current_date: effectiveCurrentDate,
    }

    const response = await axiosInstance.post(
      '/database/api/price-import/sse/',
      dataToSend,
      {
        headers: {
          'Content-Type': 'application/json',
        },
        responseType: 'text',
        onDownloadProgress: (progressEvent) => {
          if (
            progressEvent.event.currentTarget &&
            progressEvent.event.currentTarget.response
          ) {
            const dataChunk = progressEvent.event.currentTarget.response
            const lines = dataChunk.split('\n')
            lines.forEach((line) => {
              if (line.trim()) {
                try {
                  const data = JSON.parse(line)
                  window.dispatchEvent(
                    new CustomEvent('priceImportProgress', { detail: data })
                  )
                } catch (error) {
                  console.error(
                    'Error parsing progress data:',
                    error,
                    'Line:',
                    line
                  )
                }
              }
            })
          }
        },
      }
    )
    logger.log('Unknown', '[api.js] Import completed. Response:', response)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error updating price import:', error)
    if (error.response) {
      throw error.response.data
    } else if (error.request) {
      throw new Error('No response received from server')
    } else {
      throw new Error(error.message || 'Error setting up the request')
    }
  }
}

export const getAccountsTable = async (params: ApiRecord = {}): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/accounts/list_accounts/',
      params
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getAccounts = async (): Promise<Account[]> => {
  try {
    const response = await axiosInstance.get('/database/api/accounts/')
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getAccountDetails = async (accountId: number): Promise<Account> => {
  try {
    const response = await axiosInstance.get(
      `/database/api/accounts/${accountId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const createAccount = async (accountData: Partial<Account>): Promise<Account> => {
  const response = await axiosInstance.post(
    '/database/api/accounts/',
    accountData
  )
  return response.data
}

export const updateAccount = async (accountId: number, accountData: Partial<Account>): Promise<Account> => {
  try {
    const response = await axiosInstance.put(
      `/database/api/accounts/${accountId}/`,
      accountData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteAccount = async (accountId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(
      `/database/api/accounts/${accountId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getAccountFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/database/api/accounts/form_structure/'
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getFXFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/database/api/fx/form_structure/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching FX form structure:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXData = async ({
  startDate,
  endDate,
  page,
  itemsPerPage,
  sortBy,
  search,
}: {
  startDate: string
  endDate: string
  page: number
  itemsPerPage: number
  sortBy: SortBy
  search: string
}): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post('/database/api/fx/list_fx/', {
      startDate,
      endDate,
      page,
      itemsPerPage,
      sortBy,
      search,
    })
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching FX data:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXDetails = async (fxId: number): Promise<FX> => {
  try {
    const response = await axiosInstance.get(`/database/api/fx/${fxId}/`)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching FX details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addFXRate = async (fxData: Partial<FX>): Promise<FX> => {
  try {
    const response = await axiosInstance.post('/database/api/fx/', fxData)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error adding FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateFXRate = async (fxId: number, fxData: Partial<FX>): Promise<FX> => {
  try {
    const response = await axiosInstance.put(
      `/database/api/fx/${fxId}/`,
      fxData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error updating FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteFXRate = async (fxId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(`/database/api/fx/${fxId}/`)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error deleting FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXImportStats = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get('/database/api/fx/import_stats/')
    logger.log('Unknown', 'GetFXImportStats API response:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching FX import stats:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const importFXRates = async (importData: ApiRecord, signal: AbortSignal): Promise<string | ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/fx-import/sse/',
      importData,
      {
        responseType: 'text',
        signal: signal,
        headers: {
          'Content-Type': 'application/json',
        },
        onDownloadProgress: (progressEvent) => {
          if (
            progressEvent.event.currentTarget &&
            progressEvent.event.currentTarget.response
          ) {
            const dataChunk = progressEvent.event.currentTarget.response
            const lines = dataChunk.split('\n\n')
            lines.forEach((line) => {
              if (line.startsWith('data: ')) {
                try {
                  const jsonStr = line.slice(6) // Remove 'data: ' prefix
                  const data = JSON.parse(jsonStr)
                  if (data.status === 'cancelled') {
                    throw new DOMException('Import cancelled', 'AbortError')
                  }
                  window.dispatchEvent(
                    new CustomEvent('fxImportProgress', { detail: data })
                  )
                } catch (error) {
                  console.error(
                    'Error parsing progress data:',
                    error,
                    'Line:',
                    line
                  )
                }
              }
            })
          }
        },
      }
    )
    return response.data
  } catch (error) {
    if (error.name === 'AbortError') {
      logger.log('Unknown', 'FX import was aborted')
      throw error
    }
    logger.error('Unknown', 'Error importing FX rates:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const cancelFXImport = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post('/database/api/fx/cancel_import/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error cancelling FX import:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getTransactions = async (
  dateFrom: string,
  dateTo: string,
  page: number,
  itemsPerPage: number,
  search = '',
  sortBy: SortBy = {}
): Promise<PaginatedTableResponse> => {
  console.log('API request payload for transactions:', {
    dateFrom,
    dateTo,
    page,
    itemsPerPage,
    search,
    sortBy,
  })
  try {
    const response = await axiosInstance.post(
      '/transactions/api/get_transactions_table/',
      {
        page,
        itemsPerPage,
        search,
        dateFrom,
        dateTo,
        sortBy,
      }
    )
    logger.log('Unknown', 'API response for transactions:', response.data)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching transactions:', error)
    throw error
  }
}

export const getTransactionFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/transactions/api/form_structure/'
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching transaction form structure:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getTransactionDetails = async (id: number): Promise<TransactionForm> => {
  try {
    const response = await axiosInstance.get(`/transactions/api/${id}/`)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching transaction details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addTransaction = async (transactionData: Partial<TransactionForm>): Promise<TransactionForm> => {
  try {
    const response = await axiosInstance.post(
      '/transactions/api/',
      transactionData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error adding transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateTransaction = async (id: number, transactionData: Partial<TransactionForm>): Promise<TransactionForm> => {
  try {
    const response = await axiosInstance.put(
      `/transactions/api/${id}/`,
      transactionData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error updating transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteTransaction = async (id: number): Promise<void> => {
  try {
    await axiosInstance.delete(`/transactions/api/${id}/`)
  } catch (error) {
    logger.error('Unknown', 'Error deleting transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

// FX Transaction API functions
export const getFXTransactionFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/transactions/api/fx/form_structure/'
    )
    return response.data
  } catch (error) {
    logger.error(
      'Unknown',
      'Error fetching FX transaction form structure:',
      error
    )
    throw error.response ? error.response.data : error.message
  }
}

export const getFXTransactionDetails = async (id: number): Promise<FXTransactionForm> => {
  try {
    const response = await axiosInstance.get(`/transactions/api/fx/${id}/`)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching FX transaction details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addFXTransaction = async (transactionData: Partial<FXTransactionForm>): Promise<FXTransactionForm> => {
  try {
    logger.log('Unknown', 'Sending FX transaction data:', transactionData) // Add this line
    const response = await axiosInstance.post(
      '/transactions/api/fx/create_fx_transaction/',
      transactionData
    )
    logger.log('Unknown', 'Received response:', response.data) // Add this line
    return response.data
  } catch (error) {
    console.error(
      'Error adding FX transaction:',
      error.response ? error.response.data : error
    )
    throw error.response ? error.response.data : error.message
  }
}

export const updateFXTransaction = async (id: number, transactionData: Partial<FXTransactionForm>): Promise<FXTransactionForm> => {
  try {
    const response = await axiosInstance.put(
      `/transactions/api/fx/${id}/`,
      transactionData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error updating FX transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteFXTransaction = async (id: number): Promise<void> => {
  try {
    await axiosInstance.delete(`/transactions/api/fx/${id}/`)
  } catch (error) {
    logger.error('Unknown', 'Error deleting FX transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityPosition = async (
  securityId: number,
  accountId: number,
  date: string | null = null
): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/transactions/api/get_security_position/',
      {
        security_id: securityId,
        account_id: accountId,
        date: date,
      }
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error getting security position:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const transferAsset = async (transferData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/transactions/api/transfer_asset/',
      transferData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error transferring asset:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const analyzeFile = async (formData: FormData): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/transactions/api/analyze_file/',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error analyzing file:', error)
    throw error
  }
}

export async function getAccountPerformanceSummary(): Promise<ApiRecord> {
  try {
    const response = await axiosInstance.get('/summary/api/summary_data/')
    return response.data
  } catch (error) {
    if (error.response && error.response.status === 401) {
      throw new Error('Authentication required')
    }
    throw error
  }
}

export async function getPortfolioBreakdownSummary(year: number): Promise<ApiRecord> {
  try {
    const response = await axiosInstance.get(
      '/summary/api/portfolio_breakdown/',
      {
        params: { year: year },
      }
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching portfolio breakdown:', error)
    throw error
  }
}

export const getBrokerTokens = async (): Promise<ApiRecord | ApiRecord[]> => {
  logger.log('Unknown', 'getBrokerTokens called') // Debug log
  try {
    logger.log('Unknown', 'Making request to /users/api/broker_tokens/') // Debug log
    const response = await axiosInstance.get('/users/api/broker_tokens/')
    logger.log('Unknown', 'getBrokerTokens response:', response) // Debug log
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error in getBrokerTokens:', error) // Debug log
    throw error.response ? error.response.data : error.message
  }
}

export const saveTinkoffToken = async (tokenData: ApiRecord): Promise<ApiRecord> => {
  logger.log('Unknown', 'Attempting to save Tinkoff token...')
  try {
    const response = await axiosInstance.post(
      '/users/api/tinkoff-tokens/save_read_only_token/',
      tokenData
    )
    logger.log('Unknown', 'Save token response:', response)
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error saving Tinkoff token:', error.response?.data)
    throw error
  }
}

export const testTinkoffConnection = async (tokenId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      `/users/api/tinkoff-tokens/${tokenId}/test_connection/`
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error testing Tinkoff connection:', error)
    if (error.response?.data?.error === 'PERMISSION_DENIED') {
      throw new Error('Token has insufficient privileges.')
    } else if (error.response?.data?.error === 'UNAUTHENTICATED') {
      throw new Error('Token is invalid or expired.')
    }
    throw error.response ? error.response.data : error.message
  }
}

export const saveIBToken = async (tokenData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/ib-tokens/',
      tokenData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error saving IB token:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const saveBybitToken = async (tokenData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/bybit-tokens/',
      tokenData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error saving Bybit token:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const saveOKXToken = async (tokenData: ApiRecord): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/users/api/okx-tokens/',
      tokenData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error saving OKX token:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const testIBConnection = async (tokenId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      `/users/api/ib-tokens/${tokenId}/test_connection/`
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error testing IB connection:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const revokeToken = async (broker: string, tokenId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post('/users/api/revoke_token/', {
      token_type: broker,
      token_id: tokenId,
    })
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error revoking token:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteToken = async (broker: string, tokenId: number): Promise<unknown> => {
  let brokerEndpoint
  switch (broker) {
    case 'tinkoff':
      brokerEndpoint = 'tinkoff-tokens'
      break
    case 'ib':
      brokerEndpoint = 'ib-tokens'
      break
    case 'bybit':
      brokerEndpoint = 'bybit-tokens'
      break
    case 'okx':
      brokerEndpoint = 'okx-tokens'
      break
    default:
      throw new Error(`Unsupported broker type: ${broker}`)
  }

  return await axiosInstance.delete(`/users/api/${brokerEndpoint}/${tokenId}/`)
}

export const getAccountGroups = async (): Promise<AccountGroup[]> => {
  try {
    logger.log('Unknown', 'Fetching account groups') // Debug log
    const response = await axiosInstance.get('/users/api/account-groups/')
    logger.log('Unknown', 'Broker groups response:', response) // Debug log
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching account groups:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const saveAccountGroup = async (groupData: Partial<AccountGroup>): Promise<AccountGroup> => {
  try {
    logger.log('Unknown', 'Saving account group:', groupData) // Debug log
    const response = await axiosInstance.post(
      '/users/api/account-groups/',
      groupData
    )
    logger.log('Unknown', 'Save account group response:', response) // Debug log
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error saving account group:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateAccountGroup = async (groupData: AccountGroup): Promise<AccountGroup> => {
  try {
    const response = await axiosInstance.put(
      `/users/api/account-groups/${groupData.id}/`,
      groupData
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error updating account group:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteAccountGroup = async (groupId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(
      `/users/api/account-groups/${groupId}/`
    )
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error deleting account group:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getAvailableBrokers = async (): Promise<Broker[]> => {
  try {
    const response = await axiosInstance.get('/database/api/brokers/')
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching brokers:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokersTable = async (params: ApiRecord = {}): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.post(
      '/database/api/brokers/list_brokers/',
      params
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokerDetails = async (brokerId: number): Promise<Broker> => {
  try {
    const response = await axiosInstance.get(
      `/database/api/brokers/${brokerId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const createBroker = async (brokerData: Partial<Broker>): Promise<Broker> => {
  const response = await axiosInstance.post(
    '/database/api/brokers/',
    brokerData
  )
  return response.data
}

export const updateBroker = async (brokerId: number, brokerData: Partial<Broker>): Promise<Broker> => {
  try {
    const response = await axiosInstance.put(
      `/database/api/brokers/${brokerId}/`,
      brokerData
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteBroker = async (brokerId: number): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.delete(
      `/database/api/brokers/${brokerId}/`
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokerFormStructure = async (): Promise<ApiRecord> => {
  try {
    const response = await axiosInstance.get(
      '/database/api/brokers/form_structure/'
    )
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokersWithTokens = async (): Promise<Broker[]> => {
  try {
    const response = await axiosInstance.get('/database/api/brokers/', {
      params: { with_active_tokens: true },
    })
    return response.data
  } catch (error) {
    logger.error('Unknown', 'Error fetching brokers with tokens:', error)
    throw error.response ? error.response.data : error.message
  }
}
