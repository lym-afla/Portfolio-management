import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import logger from '@/utils/logger'

// Spec constant for WebSocket.readyState === OPEN. Referenced by value so
// the guard also holds in the browser-test harness, whose WebSocket proxy
// does not expose the constructor's static constants.
const WEBSOCKET_OPEN = 1

export function useWebSocket(baseUrl: string) {
  const authStore = useAuthStore()
  const socket = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const lastMessage = ref<MessageEvent | null>(null)
  const intentionalClose = ref(false)
  const connectionAttempted = ref(false)
  // Monotonic connection identity: connect() and disconnect() both bump it,
  // so every callback bound to a socket can tell whether that socket is
  // still the current one. Superseded sockets — late opens, delayed closes,
  // in-flight frames, stale error callbacks — may neither mutate shared
  // state nor trigger reconnects.
  let connectionId = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const clearReconnectTimer = () => {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

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
    clearReconnectTimer()
    return new Promise((resolve) => {
      // Set a timeout to prevent hanging if connection fails
      const connectionTimeout = setTimeout(() => {
        logger.warn('Unknown', 'WebSocket connection attempt timed out')
        resolve(false)
      }, 3000)

      // Only attempt once if already attempted. This must not allocate a
      // new connection identity: the already-open connection keeps its
      // callbacks and message ownership.
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

      // A new identity is allocated only when a new connection is actually
      // created; every handler below closes or reads ITS OWN captured
      // socket, never the shared reference (which may already point at a
      // replacement).
      const id = ++connectionId
      try {
        const url = getWebSocketUrl(baseUrl)
        logger.log('Unknown', 'Attempting to connect to WebSocket:', url)

        const ws: WebSocket = new WebSocket(url)
        socket.value = ws

        ws.onopen = () => {
          if (id !== connectionId) {
            // A superseded socket finished opening: discard IT (the local
            // instance), never the current connection.
            logger.log('Unknown', 'Discarding superseded WebSocket open')
            try {
              ws.close()
            } catch {
              // Already closing or closed.
            }
            return
          }
          logger.log('Unknown', 'WebSocket connection opened')
          isConnected.value = true
          clearTimeout(connectionTimeout)
          resolve(true)
        }

        ws.onclose = () => {
          if (id !== connectionId) {
            // Delayed close of a superseded socket: the current connection
            // is untouched.
            logger.log('Unknown', 'Ignoring superseded WebSocket close')
            return
          }
          logger.log('Unknown', 'WebSocket connection closed')
          isConnected.value = false
          if (!intentionalClose.value) {
            // Only attempt reconnect if app is fully initialized
            if (authStore.isInitialized) {
              clearReconnectTimer()
              reconnectTimer = setTimeout(() => {
                reconnectTimer = null
                if (id !== connectionId) {
                  // The reconnection belongs to a superseded connection.
                  return
                }
                connectionAttempted.value = false // Reset the flag to allow reconnect
                connect()
              }, 3000) // Reconnect after 3 seconds if not intentional
            }
          }
        }

        ws.onerror = (error) => {
          if (id !== connectionId) return
          logger.error('Unknown', 'WebSocket error:', error)
          clearTimeout(connectionTimeout)
          resolve(false)
        }

        ws.onmessage = (event) => {
          if (id !== connectionId) return
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
    connectionId += 1
    clearReconnectTimer()
    if (socket.value) {
      intentionalClose.value = true
      socket.value.close()
    }
    isConnected.value = false
  }

  const reset = () => {
    intentionalClose.value = false
    connectionAttempted.value = false
  }

  const sendMessage = (message: unknown) => {
    if (socket.value && socket.value.readyState === WEBSOCKET_OPEN) {
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
