import { ref } from 'vue'
import { useStore } from 'vuex'

export function useWebSocket(baseUrl) {
  const store = useStore()
  const socket = ref(null)
  const isConnected = ref(false)
  const lastMessage = ref(null)

  const getWebSocketUrl = (baseUrl) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.hostname
    const port = 8000
    const token = store.state.accessToken
    return `${protocol}://${host}:${port}${baseUrl}?token=${token}`
  }

  const connect = () => {
    const url = getWebSocketUrl(baseUrl)
    console.log('Attempting to connect to WebSocket:', url)
    socket.value = new WebSocket(url)

    socket.value.onopen = () => {
      isConnected.value = true
      console.log('WebSocket connection opened')
    }

    socket.value.onmessage = (event) => {
      lastMessage.value = JSON.parse(event.data)
      console.log('WebSocket message received:', lastMessage.value)
    }

    socket.value.onclose = () => {
      isConnected.value = false
      console.log('WebSocket connection closed')
    }

    socket.value.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  const disconnect = () => {
    if (socket.value) {
      socket.value.close()
    }
  }

  const sendMessage = (message) => {
    if (socket.value && isConnected.value) {
      console.log('Sending message:', message)
      socket.value.send(JSON.stringify(message))
    } else {
      console.error('Cannot send message: WebSocket is not connected')
    }
  }

  return {
    isConnected,
    lastMessage,
    sendMessage,
    connect,
    disconnect
  }
}