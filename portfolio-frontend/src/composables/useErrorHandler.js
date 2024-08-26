import { inject } from 'vue'

export function useErrorHandler() {
  const showError = inject('showError')

  const extractErrorMessage = (htmlContent) => {
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlContent, 'text/html');
    const summaryElement = doc.querySelector('#summary');
    if (summaryElement) {
      const h1 = summaryElement.querySelector('h1');
      const requestURL = summaryElement.querySelector('tr:nth-child(2) td');
      if (h1 && requestURL) {
        return `${h1.textContent.trim()} - ${requestURL.textContent.trim()}`;
      }
    }
    return 'An unexpected error occurred.';
  }

  const handleApiError = (error) => {
    let errorMessage = 'An unexpected error occurred.'

    if (error.response) {
      if (error.response.status === 404) {
        errorMessage = extractErrorMessage(error.response.data);
      } else if (error.response.data && error.response.data.detail) {
        errorMessage = error.response.data.detail
      } else if (error.response.data && typeof error.response.data === 'string') {
        errorMessage = error.response.data
      } else {
        errorMessage = `Error ${error.response.status}: ${error.response.statusText}`
      }
    } else if (error.request) {
      // The request was made but no response was received
      errorMessage = 'No response from server. Please check your internet connection.'
    } else {
      // Something happened in setting up the request that triggered an Error
      errorMessage = error.message || 'An error occurred while processing your request.'
    }

    console.error('API Error:', error)
    showError(errorMessage)
    return errorMessage
  }

  return {
    handleApiError
  }
}