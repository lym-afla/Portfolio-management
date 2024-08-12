import axios from 'axios';

export const checkAuth = async () => {
  const token = localStorage.getItem('token');
  if (!token) {
    return false;
  }

  try {
    // Make a request to a protected endpoint to verify the token
    await axios.get('/users/api/verify-token/');
    return true;
  } catch (error) {
    console.error('Token verification failed:', error);
    localStorage.removeItem('token');
    return false;
  }
};