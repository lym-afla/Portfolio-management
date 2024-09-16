import axios from 'axios';

export const checkAuth = async () => {
  const token = localStorage.getItem('token');
  if (!token) {
    return false;
  }

  try {
    // Set the token in the Authorization header
    await axios.get('/users/api/verify-token/', {
      headers: {
        'Authorization': `Token ${token}`
      }
    });
    // If the request is successful (doesn't throw an error), return true
    return true;
  } catch (error) {
    console.error('Token verification failed:', error);
    localStorage.removeItem('token');
    return false;
  }
};