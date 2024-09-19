<template>
    <div>
      <v-btn color="primary" @click="sendTestMessage">Send Test Message</v-btn>
      <v-alert v-if="messageReceived" type="success">
        Message received by backend!
      </v-alert>
    </div>
  </template>
  
  <script>
  import { ref } from 'vue'
  import { useWebSocket } from '@/composables/useWebSocket'
  
  export default {
    setup() {
      const { sendMessage, connect, isConnected } = useWebSocket('/ws/transactions/')
      const messageReceived = ref(false)
  
      const sendTestMessage = () => {
        if (isConnected.value) {
          sendMessage({
            type: 'test_message',
            content: 'This is a test message'
          })
        } else {
          console.error('WebSocket is not connected')
        }
      }
  
      connect()
  
      return {
        sendTestMessage,
        messageReceived
      }
    }
  }
  </script>