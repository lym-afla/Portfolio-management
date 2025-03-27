import { inject } from 'vue'

export function useErrorHandler() {
  const showError = inject('showError')

  const handleApiError = (error) => {
    let errorMessage = 'An unexpected error occurred.'
    console.log('handleApiError:', error)

    if (error.response) {
      if (error.response.data && error.response.data.error) {
        errorMessage = error.response.data.error
      } else if (error.response.status === 403) {
        errorMessage = 'You do not have permission to access this resource.'
      }
    } else if (error.request) {
      errorMessage =
        'The server did not respond. Please check your internet connection.'
    } else if (error.message) {
      errorMessage = error.message
    }

    showError(errorMessage)
  }

  return {
    handleApiError,
  }
}
