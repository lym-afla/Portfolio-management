<template>
  <span class="text-start text-nowrap">
    <!-- FX Transaction (handle separately to avoid space before colon) -->
    <template v-if="isFXTransaction">
      FX: {{ transaction.from_cur }} to {{ transaction.to_cur }} @{{
        formatExchangeRate(transaction.exchange_rate)
      }}
      <commission-display
        v-if="transaction.commission"
        :commission="transaction.commission"
      />
    </template>

    <template v-else>
      <template v-if="transaction.type">
        {{ transaction.type }}{{ ' ' }}
      </template>

      <!-- Cash In/Out transactions -->
      <template v-if="isCashTransaction">
        {{ transaction.cash_flow }}
        <template v-if="isDividendOrCoupon">
          for
          <security-link
            :id="transaction.security?.id"
            :name="transaction.security?.name"
          />
        </template>
      </template>

      <!-- Broker commission -->
      <template v-else-if="transaction.type === 'Broker commission'">
        {{ transaction.commission || transaction.cash_flow }}
      </template>

      <!-- Close transaction -->
      <template v-else-if="transaction.type === 'Close'">
        {{ transaction.quantity }} of
        <security-link
          :id="transaction.security?.id"
          :name="transaction.security?.name"
        />
      </template>

      <!-- Bond Redemption/Maturity -->
      <template v-else-if="isBondRedemption">
        of {{ transaction.notional_change }} {{ transaction.cur }} for
        <security-link
          :id="transaction.security?.id"
          :name="transaction.security?.name"
        />
      </template>

      <!-- Stock Split -->
      <template v-else-if="isStockSplit">
        <template v-if="transaction.split_from && transaction.split_to">
          {{ transaction.split_to }}:{{ transaction.split_from }}
        </template>
        <template v-if="transaction.quantity">
          ({{ transaction.quantity > 0 ? '+' : '' }}{{ transaction.quantity }}
          shares)
        </template>
        for
        <security-link
          :id="transaction.security?.id"
          :name="transaction.security?.name"
        />
        <span v-if="transaction.comment" class="text-grey">
          - {{ transaction.comment }}
        </span>
      </template>

      <!-- Regular transaction (Buy/Sell) -->
      <template v-else-if="isRegularTransaction">
        <template v-if="transaction.quantity && transaction.quantity !== '–'">
          {{ transaction.quantity }} @{{ transaction.price }}
        </template>
        <template v-else> @ {{ transaction.price }} </template> of
        <security-link
          :id="transaction.security?.id"
          :name="transaction.security?.name"
        />
        <commission-display
          v-if="transaction.commission"
          :commission="transaction.commission"
        />
        <aci-display v-if="transaction.aci" :aci="transaction.aci" />
      </template>

      <!-- Tax with security -->
      <template
        v-else-if="transaction.type === 'Tax' && transaction.security?.name"
      >
        for
        <security-link
          :id="transaction.security?.id"
          :name="transaction.security?.name"
        />
        <span v-if="transaction.security?.type === 'Bond'"> coupon </span>
        <span v-else> dividend </span>
      </template>
    </template>
  </span>
</template>

<script>
import { computed } from 'vue'
import SecurityLink from './SecurityLink.vue'
import CommissionDisplay from './CommissionDisplay.vue'
import AciDisplay from './AciDisplay.vue'

export default {
  name: 'TransactionDescription',
  components: {
    SecurityLink,
    CommissionDisplay,
    AciDisplay,
  },
  props: {
    transaction: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    const isBondRedemption = computed(() =>
      ['Bond redemption', 'Bond maturity'].includes(props.transaction.type)
    )

    const isCashTransaction = computed(
      () =>
        props.transaction.type?.includes('Cash') ||
        props.transaction.type === 'Dividend' ||
        props.transaction.type === 'Coupon'
    )

    const isDividendOrCoupon = computed(
      () =>
        props.transaction.type === 'Dividend' ||
        props.transaction.type === 'Coupon'
    )

    const isFXTransaction = computed(
      () =>
        props.transaction.transaction_type === 'fx' ||
        props.transaction.type === 'FX'
    )

    const isStockSplit = computed(
      () => props.transaction.type === 'Stock split'
    )

    const isRegularTransaction = computed(
      () =>
        ![
          'Broker commission',
          'Tax',
          'Interest income',
          'Bond redemption',
          'Bond maturity',
          'Stock split',
          'FX',
        ].includes(props.transaction.type) && !isCashTransaction.value
    )

    const formatExchangeRate = (rate) => {
      if (!rate) return ''
      const rateNum = parseFloat(rate)
      if (rateNum < 1 && rateNum > 0) {
        return `${(1 / rateNum).toFixed(4)}`
      }
      return rateNum.toFixed(4)
    }

    return {
      isBondRedemption,
      isCashTransaction,
      isStockSplit,
      isDividendOrCoupon,
      isFXTransaction,
      isRegularTransaction,
      formatExchangeRate,
    }
  },
}
</script>
