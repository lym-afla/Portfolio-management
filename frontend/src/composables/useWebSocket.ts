import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import logger from '@/utils/logger'

export function useWebSocket(baseUrl: string) {
  const authStore = useAuthStore()
  const socket = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const lastMessage = ref<MessageEvent | null>(null)
  const intentionalClose = ref(false)
  const connectionAttempted = ref(false)

  const getWebSocketUrl = (baseUrl: string): string => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    // Derive WebSocket host:port from VITE_API_URL so it always matches the backend
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const apiHost = apiUrl.replace(/^https?:\/\//, '').replace(/\/$/, '')
    const token = authStore.accessToken

    logger.log('Unknown', 'Token being used:', token?.substring(0, 10) + '...')

    return `${protocol}://${apiHost}${baseUrl}?token=${token}`
  }

  const connect = () => {
    return new Promise((resolve) => {
      // Set a timeout to prevent hanging if connection fails
      const connectionTimeout = setTimeout(() => {
        logger.warn('Unknown', 'WebSocket connection attempt timed out')
        resolve(false)
      }, 3000)

      // Only attempt once if already attempted
      if (connectionAttempted.value) {
        clearTimeout(connectionTimeout)
        resolve(isConnected.value)
        return
      }

      // Mark as attempted
      connectionAttempted.value = true

      if (intentionalClose.value) {
        clearTimeout(connectionTimeout)
        resolve(false)
        return
      }

      // Don't attempt connection if no token is available
      if (!authStore.accessToken) {
        logger.warn(
          'Unknown',
          'No access token available for WebSocket connection'
        )
        clearTimeout(connectionTimeout)
        resolve(false)
        return
      }

      try {
        const url = getWebSocketUrl(baseUrl)
        logger.log('Unknown', 'Attempting to connect to WebSocket:', url)

        socket.value = new WebSocket(url)

        socket.value.onopen = () => {
          logger.log('Unknown', 'WebSocket connection opened')
          isConnected.value = true
          clearTimeout(connectionTimeout)
          resolve(true)
        }

        socket.value.onclose = () => {
          logger.log('Unknown', 'WebSocket connection closed')
          isConnected.value = false
          if (!intentionalClose.value) {
            // Only attempt reconnect if app is fully initialized
            if (authStore.isInitialized) {
              setTimeout(() => {
                connectionAttempted.value = false // Reset the flag to allow reconnect
                connect()
              }, 3000) // Reconnect after 3 seconds if not intentional
            }
          }
        }

        socket.value.onerror = (error) => {
          logger.error('Unknown', 'WebSocket error:', error)
          clearTimeout(connectionTimeout)
          resolve(false)
        }

        socket.value.onmessage = (event) => {
          try {
            lastMessage.value = JSON.parse(event.data)
          } catch (e) {
            logger.error('Unknown', 'Error parsing WebSocket message:', e)
          }
        }
      } catch (error) {
        logger.error('Unknown', 'Error initializing WebSocket:', error)
        clearTimeout(connectionTimeout)
        resolve(false)
      }
    })
  }

  const disconnect = () => {
    if (socket.value) {
      intentionalClose.value = true
      socket.value.close()
    }
  }

  const reset = () => {
    intentionalClose.value = false
    connectionAttempted.value = false
  }

  const sendMessage = (message) => {
    if (socket.value && socket.value.readyState === WebSocket.OPEN) {
      logger.log('Unknown', 'Sending message:', message)
      socket.value.send(JSON.stringify(message))
      return true
    } else {
      logger.warn('Unknown', 'Cannot send message: WebSocket is not connected')
      return false
    }
  }

  // Only attempt to connect if the app is fully initialized
  if (authStore.isInitialized) {
    connect().catch((error) => {
      logger.error(
        'Unknown',
        'Failed to establish initial WebSocket connection:',
        error
      )
    })
  }

  return {
    isConnected,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
    reset,
  }
}
