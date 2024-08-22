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

export const getOpenPositions = async (fromDate, toDate, timespan, page, itemsPerPage, search = '', sortBy = {}) => {
  console.log('[api.js] getOpenPositions called with:', { fromDate, toDate, timespan, page, itemsPerPage, search, sortBy });
  try {
    const response = await axiosInstance.post(`${API_URL}/open_positions/api/get_open_positions_table/`, {
      fromDate,
      toDate,
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

export const getClosedPositions = async (fromDate, toDate, timespan, page, itemsPerPage, search = '', sortBy = {}) => {
  try {
    const response = await axiosInstance.post(`${API_URL}/closed_positions/api/get_closed_positions_table/`, {
      fromDate,
      toDate,
      timespan,
      page,
      itemsPerPage,
      search,
      sortBy  // This will be a single object or an empty object
    })
    console.log('API request payload:', { fromDate, toDate, timespan, page, itemsPerPage, search, sortBy })
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
    const response = await axiosInstance.get(`${API_URL}/database/api/asset-types/`);
    return response.data;
  } catch (error) {
    throw error.response ? error.response.data : error.message;
  }
};

export const getBrokers = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/brokers/`);
    return response.data;
  } catch (error) {
    throw error.response ? error.response.data : error.message;
  }
};

export const getSecurities = async () => {
  try {
    const response = await axiosInstance.get(`${API_URL}/database/api/securities/`);
    return response.data;
  } catch (error) {
    throw error.response ? error.response.data : error.message;
  }
};