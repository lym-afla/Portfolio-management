<template>
  <div>
    <v-btn color="primary" @click="sendTestMessage">Send Test Message</v-btn>
    <v-alert v-if="messageReceived" type="success">
      Message received by backend!
    </v-alert>
  </div>
</template>

<script>
import { ref, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export default {
  setup() {
    const { sendMessage, connect, isConnected, lastMessage } =
      useWebSocket('/ws/transactions/')
    const messageReceived = ref(false)

    const sendTestMessage = () => {
      if (isConnected.value) {
        sendMessage({
          type: 'test_message',
          content: 'This is a test message',
        })
      } else {
        console.error('WebSocket is not connected')
      }
    }

    connect()

    watch(lastMessage, (newMessage) => {
      if (newMessage) {
        messageReceived.value = true
      }
    })

    return {
      sendTestMessage,
      messageReceived,
    }
  },
}
</script>
