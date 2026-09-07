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

<script setup>
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

const props = defineProps({
  summary: {
    type: Object,
    required: true,
  },
  currency: {
    type: String,
    default: 'USD',
  },
})

const appStore = useAppStore()

function formatKey(key) {
  return key
    .replaceAll('_', ' ')
    .replace(/^./, (str) => str.toUpperCase())
    .replace(/irr/gi, 'IRR')
    .replace(/nav/gi, 'NAV')
}

const formatAccountSelection = computed(() => {
  const selection = appStore.accountSelection
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
</script>

<style scoped>
.summary-card {
  border: 1px solid rgb(var(--v-theme-surface-variant, 226, 230, 235));
  box-shadow: none;
}

.summary-card .v-card-title {
  color: rgb(var(--v-theme-primary));
  font-size: 1.25rem;
}

.text-subtitle-2 {
  color: rgb(var(--v-theme-secondary));
  font-size: 0.875rem;
}
</style>
