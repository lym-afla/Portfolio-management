<template>
  <tr>
    <td v-if="showActions" />
    <td>{{ transaction.date }}</td>
    
    <!-- Broker - Account column -->
    <template v-if="showBrokerAccount">
      <td class="text-start">
        {{ brokerAccountLabel }}
      </td>
    </template>

    <td class="text-start">
      <transaction-description :transaction="transaction" />
    </td>
    <td class="text-center">{{ displayType }}</td>

    <!-- Cash Flow columns (per currency) -->
    <template v-if="showCashFlow">
      <td
        v-for="currency in currencies"
        :key="`cash_flow-${currency}`"
        class="text-center"
      >
        <transaction-cash-flow
          :transaction="transaction"
          :currency="currency"
        />
      </td>
    </template>

    <!-- Single cash flow column (for security detail page) -->
    <template v-if="showSingleCashFlow">
      <td class="text-center">
        <template
          v-if="
            ['Dividend', 'Tax', 'Coupon'].includes(transaction.type) ||
            transaction.type.includes('Interest') ||
            transaction.type.includes('Cash') ||
            transaction.type.includes('Bond')
          "
        >
          {{ transaction.cash_flow }}
        </template>
        <template v-else>
          {{ transaction.cash_flow }}
        </template>
      </td>
    </template>

    <!-- Spacer -->
    <td v-if="showBalances" class="text-center" />

    <!-- Balance columns (per currency) -->
    <template v-if="showBalances">
      <td
        v-for="currency in currencies"
        :key="`balance-${currency}`"
        class="text-center"
      >
        {{ transaction.balances?.[currency] || '–' }}
      </td>
    </template>

    <!-- Actions: named Vuetify buttons whose accessible identity carries the
         row's date plus available account/security text; the emitted payload
         stays the unchanged transaction object. -->
    <td v-if="showActions" class="text-end">
      <v-btn
        icon="mdi-pencil"
        variant="text"
        size="small"
        :aria-label="editActionLabel"
        class="workspace-row-action"
        @click="$emit('edit', transaction)"
      />
      <v-btn
        icon="mdi-delete"
        variant="text"
        size="small"
        :aria-label="deleteActionLabel"
        class="workspace-row-action"
        @click="$emit('delete', transaction)"
      />
    </td>
  </tr>
</template>

<script setup>
import { computed } from 'vue'
import TransactionDescription from './TransactionDescription.vue'
import TransactionCashFlow from './TransactionCashFlow.vue'
import { displayTransactionType } from '@/utils/formatUtils'

const props = defineProps({
  transaction: {
    type: Object,
    required: true,
  },
  currencies: {
    type: Array,
    default: () => [],
  },
  showBalances: {
    type: Boolean,
    default: false,
  },
  showActions: {
    type: Boolean,
    default: true,
  },
  showCashFlow: {
    type: Boolean,
    default: false,
  },
  showSingleCashFlow: {
    type: Boolean,
    default: false,
  },
  showBrokerAccount: {
    type: Boolean,
    default: false,
  },
})
defineEmits(['edit', 'delete'])

const brokerAccountLabel = computed(() => {
  if (!props.transaction.account) return ''
  const parts = []
  if (props.transaction.account.broker_name) parts.push(props.transaction.account.broker_name)
  if (props.transaction.account.name) parts.push(props.transaction.account.name)
  return parts.join(' — ')
})

// Display the type label (crypto trades show 'Buy'/'Sell'; stored type unchanged).
const displayType = computed(() => displayTransactionType(props.transaction.type))

// Accessible action identity: date always, account/security when available.
const rowIdentity = computed(() => {
  const parts = []
  if (brokerAccountLabel.value) parts.push(brokerAccountLabel.value)
  const securityName = props.transaction.security?.name
  if (securityName) parts.push(securityName)
  const identity = parts.join(' — ')
  return `${displayType.value} transaction on ${props.transaction.date}${identity ? `: ${identity}` : ''}`
})
const editActionLabel = computed(() => `Edit ${rowIdentity.value}`)
const deleteActionLabel = computed(() => `Delete ${rowIdentity.value}`)
</script>
