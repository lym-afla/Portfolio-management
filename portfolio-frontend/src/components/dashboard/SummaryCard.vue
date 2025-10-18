<template>
  <v-card class="summary-card">
    <v-card-title class="text-h5 font-weight-bold">
      <v-icon left color="primary" class="mr-2">mdi-chart-box</v-icon>
      Portfolio Summary
      <div class="text-subtitle-2 mt-1">
        {{ formatAccountSelection }}
      </div>
    </v-card-title>
    <v-card-text class="pa-0">
      <v-table density="compact">
        <thead>
          <tr>
            <th />
            <th class="text-right">{{ props.currency }}</th>
          </tr>
        </thead>
        <tbody class="font-weight-bold">
          <tr v-for="(value, key) in props.summary" :key="key">
            <td class="text-left">{{ formatKey(key) }}</td>
            <td class="text-right">{{ value }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>
  </v-card>
</template>

<script>
import { computed } from 'vue'
import { useStore } from 'vuex'

export default {
  name: 'SummaryCard',
  props: {
    summary: {
      type: Object,
      required: true,
    },
    currency: {
      type: String,
      default: 'USD',
    },
  },
  setup(props) {
    const store = useStore()

    const formatKey = (key) => {
      return key
        .replace('_', ' ')
        .replace(/^./, (str) => str.toUpperCase())
        .replace('Irr', 'IRR')
    }

    const formatAccountSelection = computed(() => {
      console.log(
        '[SummaryCard]',
        store.state.accountSelection,
        store.state.selectedCurrency,
        store.state.user
      )
      const selection = store.state.accountSelection
      if (selection.type === 'all') {
        return 'All Accounts'
      } else if (selection.type === 'broker') {
        return `All accounts for broker`
      } else if (selection.type === 'group') {
        return `Account group`
      } else if (selection.type === 'account') {
        return `Individual account`
      }
      return ''
    })

    return {
      props,
      formatKey,
      formatAccountSelection,
    }
  },
}
</script>

<style scoped>
.summary-card {
  background-color: #f8f9fa !important;
  border-left: 4px solid var(--v-primary-base) !important;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
  padding-bottom: 10px;
}

.summary-card .v-card-title {
  color: var(--v-primary-base);
  font-size: 1.5rem !important;
  padding-top: 16px;
  padding-bottom: 16px;
}

.text-subtitle-2 {
  color: rgba(0, 0, 0, 0.6);
  font-size: 0.875rem;
}

.summary-card .v-table {
  background-color: transparent !important;
}

.summary-card .v-table th {
  font-weight: bold !important;
  font-size: 1.1rem;
}

.summary-card .v-table td {
  font-size: 1.05rem;
}
</style>
