import { inject } from 'vue'

export function useErrorHandler() {
  const showError = inject('showError')

  const handleApiError = (error) => {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      if (error.response.data && error.response.data.errors) {
        // If the server sends detailed error messages
        const errorMessages = Object.values(error.response.data.errors).flat()
        showError(errorMessages.join(' '))
      } else {
        showError(`Error: ${error.response.status} - ${error.response.statusText}`)
      }
    } else if (error.request) {
      // The request was made but no response was received
      showError('No response from server. Please check your internet connection.')
    } else {
      // Something happened in setting up the request that triggered an Error
      showError('An error occurred while processing your request.')
    }
    console.error('API Error:', error)
  }

  return {
    handleApiError
  }
}