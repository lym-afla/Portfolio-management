<template>
  <v-data-table
    :headers="headers"
    :items="transactions"
    :items-per-page="5"
    class="elevation-1"
  >
    <template v-slot:item="{ item }">
      <v-chip :color="getTypeColor(item.type)">{{ item.type }}</v-chip>
    </template>
  </v-data-table>
</template>

<script>
import { ref } from 'vue'

export default {
  name: 'TransactionsTable',
  props: {
    transactions: {
      type: Array,
      required: true,
      default: () => []
    }
  },
  setup() {
    const headers = ref([
      { title: 'Date', key: 'date' },
      { title: 'Type', key: 'type' },
      { title: 'Quantity', key: 'quantity' },
      { title: 'Price', key: 'price' },
      { title: 'Total', key: 'total' }
    ])

    const getTypeColor = (type) => {
      switch (type) {
        case 'Buy':
          return 'green'
        case 'Sell':
          return 'red'
        case 'Dividend':
          return 'blue'
        default:
          return 'grey'
      }
    }

    return {
      headers,
      getTypeColor
    }
  }
}
</script>
