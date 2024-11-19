import { ref } from 'vue'
import { useStore } from 'vuex'

export function useWebSocket(baseUrl) {
  const store = useStore()
  const socket = ref(null)
  const isConnected = ref(false)
  const lastMessage = ref(null)
  const intentionalClose = ref(false)

  const getWebSocketUrl = (baseUrl) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.hostname
    const port = 8000
    const token = store.state.accessToken
    
    console.log('Token being used:', token)
    
    return `${protocol}://${host}:${port}${baseUrl}?token=${token}`
  }

  const connect = () => {
    return new Promise((resolve, reject) => {
      if (intentionalClose.value) {
        resolve(false)
        return
      }

      const url = getWebSocketUrl(baseUrl)
      console.log('Attempting to connect to WebSocket:', url)
      
      if (!store.state.accessToken) {
        console.error('No access token available')
        reject(new Error('No access token available'))
        return
      }

      socket.value = new WebSocket(url)

      socket.value.onopen = () => {
        console.log('WebSocket connection opened')
        isConnected.value = true
        resolve(true)
      }

      socket.value.onclose = () => {
        console.log('WebSocket connection closed')
        isConnected.value = false
        if (!intentionalClose.value) {
          setTimeout(connect, 3000) // Reconnect after 3 seconds if not intentional
        }
      }

      socket.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        reject(error)
      }

      socket.value.onmessage = (event) => {
        try {
          lastMessage.value = JSON.parse(event.data)
        } catch (e) {
          console.error('Error parsing WebSocket message:', e)
        }
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
  }

  const sendMessage = (message) => {
    console.log('WebSocket readyState:', socket.value?.readyState)
    if (socket.value && socket.value.readyState === WebSocket.OPEN) {
      console.log('Sending message:', message)
      socket.value.send(JSON.stringify(message))
      return true
    } else {
      console.error('Cannot send message: WebSocket is not connected')
      return false
    }
  }

  return {
    isConnected,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
    reset
  }
}