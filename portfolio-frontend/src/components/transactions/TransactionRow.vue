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
    <td class="text-center">{{ transaction.type }}</td>

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

    <!-- Actions -->
    <td v-if="showActions" class="text-end">
      <v-icon small class="mr-2" @click="$emit('edit', transaction)">
        mdi-pencil
      </v-icon>
      <v-icon small @click="$emit('delete', transaction)"> mdi-delete </v-icon>
    </td>
  </tr>
</template>

<script>
import TransactionDescription from './TransactionDescription.vue'
import TransactionCashFlow from './TransactionCashFlow.vue'

export default {
  name: 'TransactionRow',
  components: {
    TransactionDescription,
    TransactionCashFlow,
  },
  props: {
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
  },
  emits: ['edit', 'delete'],
  computed: {
    brokerAccountLabel() {
      if (!this.transaction.account) return ''
      const parts = []
      if (this.transaction.account.broker_name) parts.push(this.transaction.account.broker_name)
      if (this.transaction.account.name) parts.push(this.transaction.account.name)
      return parts.join(' — ')
    },
  },
}
</script>
