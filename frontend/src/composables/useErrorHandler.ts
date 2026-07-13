import { inject } from 'vue'
import logger from '@/utils/logger'

export function useErrorHandler() {
  const showError = inject<(message: string) => void>('showError')

  const handleApiError = (error: unknown): string => {
    let errorMessage = 'An unexpected error occurred.'
    logger.log('Unknown', 'handleApiError:', error)

    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as { response?: { data?: { error?: string }; status?: number } }
      if (axiosError.response?.data?.error) {
        errorMessage = axiosError.response.data.error
      } else if (axiosError.response?.status === 403) {
        errorMessage = 'You do not have permission to access this resource.'
      }
    } else if (error && typeof error === 'object' && 'request' in error) {
      errorMessage =
        'The server did not respond. Please check your internet connection.'
    } else if (error instanceof Error && error.message) {
      errorMessage = error.message
    }

    showError?.(errorMessage)
    return errorMessage
  }

  return {
    handleApiError,
  }
}
