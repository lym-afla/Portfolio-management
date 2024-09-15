import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

export function useWebSocket() {
  const socket = ref(null)
  const isConnected = ref(false)
  const lastMessage = ref(null)

  const connect = () => {
    socket.value = io('http://localhost:8000', {
      transports: ['websocket'],
      autoConnect: false
    })

    socket.value.on('connect', () => {
      isConnected.value = true
      console.log('WebSocket connected')
    })

    socket.value.on('disconnect', () => {
      isConnected.value = false
      console.log('WebSocket disconnected')
    })

    socket.value.on('message', (data) => {
      lastMessage.value = data
      console.log('Received message:', data)
    })

    socket.value.connect()
  }

  const disconnect = () => {
    if (socket.value) {
      socket.value.disconnect()
    }
  }

  const sendMessage = (message) => {
    if (socket.value && isConnected.value) {
      socket.value.emit('message', message)
    }
  }

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    isConnected,
    lastMessage,
    sendMessage
  }
}