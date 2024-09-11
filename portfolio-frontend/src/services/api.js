import axios from 'axios'
import store from '@/store'  // Import your Vuex store

const API_URL = 'http://localhost:8000'  // Adjust this to your Django API URL

const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true
});

// Add a request interceptor
axiosInstance.interceptors.request.use(
  (config) => {
    const token = store.state.token;
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export const login = async (username, password) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/login/`, { username, password })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const register = async (username, email, password) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/register/`, { username, email, password })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getOpenPositions = async (dateFrom, dateTo, timespan, page, itemsPerPage, search = '', sortBy = {}) => {
  console.log('[api.js] getOpenPositions called with:', { dateFrom, dateTo, timespan, page, itemsPerPage, search, sortBy });
  try {
    const response = await axiosInstance.post(`${API_URL}/open_positions/api/get_open_positions_table/`, {
      dateFrom,
      dateTo,
      timespan,
      page,
      itemsPerPage,
      search,
      sortBy
    })
    return response.data
  } catch (error) {
    console.error('Error fetching open positions:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getClosedPositions = async (dateFrom, dateTo, timespan, page, itemsPerPage, search = '', sortBy = {}) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/closed_positions/api/get_closed_positions_table/`, {
      dateFrom,
      dateTo,
      timespan,
      page,
      itemsPerPage,
      search,
      sortBy  // This will be a single object or an empty object
    })
    console.log('API request payload:', { dateFrom, dateTo, timespan, page, itemsPerPage, search, sortBy })
    console.log('API response:', response.data)
    if (response.data && response.data.portfolio_closed && Array.isArray(response.data.portfolio_closed)) {
      return response.data
    } else {
      console.error('Unexpected response format:', response.data)
      throw new Error('Invalid response format')
    }
  } catch (error) {
    console.error('Error fetching closed positions:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getYearOptions = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/api/get-year-options/`)
    return response.data.table_years
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokerChoices = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/users/api/get_broker_choices/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateUserBroker = async (brokerOrGroupName) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/update_user_broker/`, { broker_or_group_name: brokerOrGroupName })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getUserProfile = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/users/api/profile/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const editUserProfile = async (profileData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/profile/edit/`, profileData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const changePassword = async (passwordData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/change-password/`, passwordData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getUserSettings = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/users/api/settings/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateUserSettings = async (settings) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/settings/`, settings)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSettingsChoices = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/users/api/settings/choices/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const logout = async () => {
  try {
    const response = await axiosInstance.post(`${API_URL}/users/api/logout/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteAccount = async () => {
  try {
    const response = await axiosInstance.delete(`${API_URL}/users/api/delete-account/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getDashboardSettings = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/users/api/dashboard-settings/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateDashboardSettings = async (settings) => {
  try {
    console.log('Sending settings to API:', settings)
    const response = await axiosInstance.post(`${API_URL}/users/api/update-settings-from-dashboard/`, settings, {
      withCredentials: true
    })
    console.log('API response:', response.data)
    return response.data
  } catch (error) {
    if (error.response && error.response.data) {
      return error.response.data
    }
    throw error
  }
}

export const getEffectiveCurrentDate = async () => {
  const response = await axiosInstance.get(`${API_URL}/api/effective-current-date/`)
  return response.data
}

export const getAssetTypes = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/get-asset-types/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

// export const getBrokers = async () => {
//   try {
//     const response = await axiosInstance.get(`${API_URL}/database/api/get-brokers/`)
//     return response.data
//   } catch (error) {
//     throw error.response ? error.response.data : error.message
//   }
// }

export const getSecurities = async (assetTypes = [], brokerId = null) => {
  try {
    const params = new URLSearchParams()
    if (assetTypes.length > 0) {
      params.append('asset_types', assetTypes.join(','))
    }
    if (brokerId) {
      params.append('broker_id', brokerId)
    }
    const response = await axiosInstance.get(`${API_URL}/database/api/get-securities/`, { params })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPrices = async (params) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/get-prices-table/`, params)
    return response.data
  } catch (error) {
    console.error('Error fetching prices:', error)
    throw error.response ? error.response.data : error.message
  }
}

// export const getBrokersForDatabase = async (params) => {
//   try {
//     const response = await axiosInstance.post(`${API_URL}/database/api/get-brokers-for-database/`, params)
//     return response.data
//   } catch (error) {
//     throw error.response ? error.response.data : error.message
//   }
// }

// export const createBroker = async (brokerData) => {
//   try {
//     const response = await axiosInstance.post(`${API_URL}/database/api/create-broker/`, brokerData)
//     return response.data
//   } catch (error) {
//     throw error.response ? error.response.data : error.message
//   }
// }

// export const updateBroker = async (brokerId, brokerData) => {
//   try {
//     const response = await axiosInstance.put(`${API_URL}/database/api/update-broker/${brokerId}/`, brokerData)
//     return response.data
//   } catch (error) {
//     throw error.response ? error.response.data : error.message
//   }
// }

// export const deleteBroker = async (brokerId) => {
//   try {
//     const response = await axiosInstance.delete(`${API_URL}/database/api/delete-broker/${brokerId}/`)
//     return response.data
//   } catch (error) {
//     throw error.response ? error.response.data : error.message
//   }
// }

export const getSecuritiesForDatabase = async (params) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/get-securities-for-database/`, params)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const createSecurity = async (securityData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/create-security/`, securityData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateSecurity = async (securityId, securityData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/database/api/update-security/${securityId}/`, securityData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteSecurity = async (securityId) => {
  try {
    const response = await axiosInstance.delete(`${API_URL}/database/api/delete-security/${securityId}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getDashboardBreakdown = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/dashboard/api/get-breakdown/`)
    return response.data
  } catch (error) {
    console.error('Error fetching breakdown data:', error)
    throw error
  }
}

export const getDashboardSummaryOverTime = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/dashboard/api/get-summary-over-time/`)
    return response.data
  } catch (error) {
    console.error('Error fetching summary over time data:', error)
    throw error
  }
}

export const getNAVChartData = async (breakdown, frequency, dateFrom, dateTo) => {
  try {
    console.log('API request params for NAV chart:', {
      breakdown: breakdown,
      frequency: frequency,
      dateFrom: dateFrom,
      dateTo: dateTo
    })
    const response = await axiosInstance.get(`${API_URL}/dashboard/api/get-nav-chart-data/`, { 
      params: {
        breakdown,
        frequency,
        dateFrom,
        dateTo
      }
    })
    console.log('API response:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching NAV chart data:', error)
    throw error
  }
}

export const getDashboardSummary = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/dashboard/api/get-summary/`)
    return response.data
  } catch (error) {
    console.error('Error fetching dashboard summary:', error)
    throw error
  }
}

export const getBrokerPerformanceFormData = async () => {
  const response = await axiosInstance.get(`${API_URL}/database/api/update-broker-performance/`)
  return response.data
}

export const updateBrokerPerformance = async (formData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/update-broker-performance/`, formData, {
      responseType: 'text',
      onDownloadProgress: (progressEvent) => {
        if (progressEvent.event.currentTarget && progressEvent.event.currentTarget.response) {
          const dataChunk = progressEvent.event.currentTarget.response
          const lines = dataChunk.split('\n')
          lines.forEach((line) => {
            if (line) {
              try {
                const data = JSON.parse(line)
                window.dispatchEvent(new CustomEvent('brokerPerformanceUpdateProgress', { detail: data }))
              } catch (error) {
                console.error('Error parsing progress data:', error, 'Line:', line)
              }
            }
          })
        }
      }
    })
    return response.data
  } catch (error) {
    console.error('Error updating broker performance:', error)
    if (error.response) {
      throw error.response.data
    } else if (error.request) {
      throw new Error('No response received from server')
    } else {
      throw new Error('Error setting up the request')
    }
  }
}

export const addPrice = async (priceData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/add-price/`, priceData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deletePrice = async (priceId) => {
  try {
    const response = await axiosInstance.delete(`${API_URL}/database/api/delete-price/${priceId}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPriceDetails = async (priceId) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/get-price-details/${priceId}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updatePrice = async (priceId, priceData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/database/api/update-price/${priceId}/`, priceData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/security-form-structure/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getSecurityDetails = async (id) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/get-security-details/${id}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getPriceImportFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/price-import/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const importPrices = async (importData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/price-import/`, importData, {
      responseType: 'text',
      onDownloadProgress: (progressEvent) => {
        console.log('Progress event:', progressEvent)
        if (progressEvent.event.currentTarget && progressEvent.event.currentTarget.response) {
          const dataChunk = progressEvent.event.currentTarget.response
          console.log('Data chunk:', dataChunk)
          const lines = dataChunk.split('\n')
          lines.forEach((line) => {
            if (line) {
              try {
                const data = JSON.parse(line)
                window.dispatchEvent(new CustomEvent('priceImportProgress', { detail: data }))
              } catch (error) {
                console.error('Error parsing progress data:', error, 'Line:', line)
              }
            }
          })
        } else {
          console.warn('Progress event does not contain expected data:', progressEvent)
        }
      }
    })
    console.log('Import completed. Response:', response)
    return response.data
  } catch (error) {
    console.error('Error importing prices:', error)
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('Error response:', error.response)
      throw error.response.data
    } else if (error.request) {
      // The request was made but no response was received
      console.error('Error request:', error.request)
      throw new Error('No response received from server')
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('Error message:', error.message)
      throw new Error('Error setting up the request')
    }
  }
}

export const getBrokersTable = async (params = {}) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/brokers/list_brokers/`, params)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokers = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/brokers/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokerDetails = async (brokerId) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/brokers/${brokerId}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const createBroker = async (brokerData) => {
  const response = await axiosInstance.post(`${API_URL}/database/api/brokers/`, brokerData)
  return response.data
}

export const updateBroker = async (brokerId, brokerData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/database/api/brokers/${brokerId}/`, brokerData)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const deleteBroker = async (brokerId) => {
  try {
    const response = await axiosInstance.delete(`${API_URL}/database/api/brokers/${brokerId}/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokerFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/brokers/form_structure/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getFXFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/fx/form_structure/`)
    return response.data
  } catch (error) {
    console.error('Error fetching FX form structure:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXData = async ({ startDate, endDate, page, itemsPerPage, sortBy, search }) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/fx/list_fx/`, {
      startDate,
      endDate,
      page,
      itemsPerPage,
      sortBy,
      search
    })
    return response.data
  } catch (error) {
    console.error('Error fetching FX data:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXDetails = async (fxId) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/fx/${fxId}/`)
    return response.data
  } catch (error) {
    console.error('Error fetching FX details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addFXRate = async (fxData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/fx/`, fxData)
    return response.data
  } catch (error) {
    console.error('Error adding FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateFXRate = async (fxId, fxData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/database/api/fx/${fxId}/`, fxData)
    return response.data
  } catch (error) {
    console.error('Error updating FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteFXRate = async (fxId) => {
  try {
    const response = await axiosInstance.delete(`${API_URL}/database/api/fx/${fxId}/`)
    return response.data
  } catch (error) {
    console.error('Error deleting FX rate:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXImportStats = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/fx/import_stats/`)
    console.log('GetFXImportStats API response:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching FX import stats:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const importFXRates = async (importOption, signal) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/fx/import_fx_rates/`, 
      { import_option: importOption },
      {
        responseType: 'text',
        signal: signal,
        onDownloadProgress: (progressEvent) => {
          if (progressEvent.event.currentTarget && progressEvent.event.currentTarget.response) {
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
                  window.dispatchEvent(new CustomEvent('fxImportProgress', { detail: data }))
                } catch (error) {
                  console.error('Error parsing progress data:', error, 'Line:', line)
                }
              }
            })
          }
        }
      }
    )
    return response.data
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('FX import was aborted')
      throw error
    }
    console.error('Error importing FX rates:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const cancelFXImport = async () => {
  try {
    const response = await axiosInstance.post(`${API_URL}/database/api/fx/cancel_import/`)
    return response.data
  } catch (error) {
    console.error('Error cancelling FX import:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getTransactions = async (dateFrom, dateTo, page, itemsPerPage, search = '', sortBy = {}) => {
  console.log('API request payload for transactions:', { dateFrom, dateTo, page, itemsPerPage, search, sortBy })
  try {
    const response = await axiosInstance.post(`${API_URL}/transactions/api/get_transactions_table/`, {
      page,
      itemsPerPage,
      search,
      dateFrom,
      dateTo,
      sortBy
    })
    console.log('API response for transactions:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching transactions:', error)
    throw error
  }
}

export const getTransactionFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/transactions/api/form_structure/`)
    return response.data
  } catch (error) {
    console.error('Error fetching transaction form structure:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getTransactionDetails = async (id) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/transactions/api/${id}/`)
    return response.data
  } catch (error) {
    console.error('Error fetching transaction details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addTransaction = async (transactionData) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/transactions/api/`, transactionData)
    return response.data
  } catch (error) {
    console.error('Error adding transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateTransaction = async (id, transactionData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/transactions/api/${id}/`, transactionData)
    return response.data
  } catch (error) {
    console.error('Error updating transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteTransaction = async (id) => {
  try {
    await axiosInstance.delete(`${API_URL}/transactions/api/${id}/`)
  } catch (error) {
    console.error('Error deleting transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

// FX Transaction API functions
export const getFXTransactionFormStructure = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/transactions/api/fx/form_structure/`)
    return response.data
  } catch (error) {
    console.error('Error fetching FX transaction form structure:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const getFXTransactionDetails = async (id) => {
  try {
    const response = await axiosInstance.get(`${API_URL}/transactions/api/fx/${id}/`)
    return response.data
  } catch (error) {
    console.error('Error fetching FX transaction details:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const addFXTransaction = async (transactionData) => {
  try {
    console.log('Sending FX transaction data:', transactionData)  // Add this line
    const response = await axiosInstance.post(`${API_URL}/transactions/api/fx/create_fx_transaction/`, transactionData)
    console.log('Received response:', response.data)  // Add this line
    return response.data
  } catch (error) {
    console.error('Error adding FX transaction:', error.response ? error.response.data : error)
    throw error.response ? error.response.data : error.message
  }
}

export const updateFXTransaction = async (id, transactionData) => {
  try {
    const response = await axiosInstance.put(`${API_URL}/transactions/api/fx/${id}/`, transactionData)
    return response.data
  } catch (error) {
    console.error('Error updating FX transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

export const deleteFXTransaction = async (id) => {
  try {
    await axiosInstance.delete(`${API_URL}/transactions/api/fx/${id}/`)
  } catch (error) {
    console.error('Error deleting FX transaction:', error)
    throw error.response ? error.response.data : error.message
  }
}

// export const analyzeFile = async (file) => {
//   const formData = new FormData()
//   formData.append('file', file)

//   try {
//     const response = await axiosInstance.post(`${API_URL}/transactions/api/analyze_file/`, formData, {
//       headers: {
//         'Content-Type': 'multipart/form-data'
//       }
//     })
//     return response.data
//   } catch (error) {
//     console.error('Error analyzing file:', error)
//     // throw error.response ? error.response.data : error.message
//     throw error
//   }
// }

export const analyzeFile = async (formData) => {
  try {
    const response = await axios.post(`${API_URL}/transactions/api/analyze_file/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  } catch (error) {
    console.error('Error analyzing file:', error)
    throw error
  }
}

export const importTransactions = async (fileId, brokerId) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/transactions/api/import_transactions/`, {
      file_id: fileId,
      broker_id: brokerId
    })
    return response.data
  } catch (error) {
    console.error('Error importing transactions:', error)
    // throw error.response ? error.response.data : error.message
    throw error
  }
}
