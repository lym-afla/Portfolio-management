<template>
  <template v-if="isRegularTransaction">
    <!-- Regular transaction in matching currency -->
    <template v-if="transaction.cur === currency">
      {{ transaction.cash_flow }}
    </template>
    <template v-else>–</template>
  </template>

  <template v-else-if="isFXTransaction">
    <!-- FX transaction: show from_amount, to_amount, or commission in third currency -->
    <template v-if="transaction.from_cur === currency">
      {{ transaction.from_amount }}
    </template>
    <template v-else-if="transaction.to_cur === currency">
      {{ transaction.to_amount }}
    </template>
    <template v-else-if="hasCommissionInCurrency">
      {{ transaction.commission }}
    </template>
    <template v-else>–</template>
  </template>

  <template v-else>–</template>
</template>

<script>
import { computed } from 'vue'

export default {
  name: 'TransactionCashFlow',
  props: {
    transaction: {
      type: Object,
      required: true,
    },
    currency: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    const isFXTransaction = computed(
      () =>
        props.transaction.transaction_type === 'fx' ||
        props.transaction.type === 'FX'
    )

    const isRegularTransaction = computed(
      () =>
        props.transaction.transaction_type === 'regular' ||
        !isFXTransaction.value
    )

    // Check if FX transaction has commission in this currency (third currency case)
    const hasCommissionInCurrency = computed(() => {
      if (!isFXTransaction.value) return false

      // Commission exists and this currency matches the commission_currency
      // AND it's not the from or to currency (those already include commission)
      return (
        props.transaction.commission &&
        props.transaction.commission_currency === props.currency &&
        props.currency !== props.transaction.from_cur &&
        props.currency !== props.transaction.to_cur
      )
    })

    return {
      isFXTransaction,
      isRegularTransaction,
      hasCommissionInCurrency,
    }
  },
}
</script>
