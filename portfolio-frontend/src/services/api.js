import axios from 'axios'

const API_URL = 'http://localhost:8000'  // Adjust this to your Django API URL

export const login = async (username, password) => {
  try {
    const response = await axios.post(`${API_URL}/users/api/login/`, { username, password })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const register = async (username, email, password) => {
  try {
    const response = await axios.post(`${API_URL}/users/api/register/`, { username, email, password })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getClosedPositions = async (timespan, page, itemsPerPage, search = '') => {
  try {
    const response = await axios.post(`${API_URL}/closed_positions/api/get_closed_positions_table/`, {
      timespan,
      page,
      items_per_page: itemsPerPage,
      search
    })
    // Check if the response has the expected structure
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
    const response = await axios.get(`${API_URL}/closed_positions/api/get_year_options/`)
    return response.data.closed_table_years
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const getBrokers = async () => {
  try {
    const response = await axios.get(`${API_URL}/users/api/get_brokers/`)
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}

export const updateUserBroker = async (brokerOrGroupName) => {
  try {
    const response = await axios.post(`${API_URL}/users/api/update_user_broker/`, { broker_or_group_name: brokerOrGroupName })
    return response.data
  } catch (error) {
    throw error.response ? error.response.data : error.message
  }
}