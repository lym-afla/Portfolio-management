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
        errorMessage = extractErrorMessage(error.response.data)
      } else if (error.response.data && error.response.data.error) {
        errorMessage = error.response.data.error
      } else if (error.response.status === 403) {
        errorMessage = 'You do not have permission to access this resource.'
      }
    } else if (error.request) {
      errorMessage = 'The server did not respond. Please check your internet connection.'
    }

    showError(errorMessage)
  }

  return {
    handleApiError
  }
}