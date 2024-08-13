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

// Add other API calls as needed