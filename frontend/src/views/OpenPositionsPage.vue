<template>
  <PositionsPageBase
    :fetch-positions="fetchOpenPositions"
    :headers="openPositionsHeaders"
    :default-visible-keys="openDefaultVisibleKeys"
    page-title="Open Positions"
  >
    <template #above-table>
      <v-card class="mb-4">
        <v-card-title class="text-h6">Cash Balances</v-card-title>
        <v-card-text>
          <v-skeleton-loader
            v-if="cashBalancesLoading"
            type="table-row-divider@3"
          />
          <v-table v-else density="compact">
            <tbody>
              <tr v-for="(balance, currency) in cashBalances" :key="currency">
                <td class="text-left">{{ currency }}</td>
                <td class="text-right">{{ balance }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </template>

    <template
      v-for="key in percentageColumns"
      :key="key"
      #[`item.${key}`]="{ item }"
    >
      <span v-if="item && item[key] !== undefined" class="font-italic">{{
        item[key]
      }}</span>
      <span v-else>-</span>
    </template>

    <template #[`item.name`]="{ item }">
      <router-link
        :to="{ name: 'SecurityDetail', params: { id: item.id } }"
        class="text-decoration-none"
      >
        {{ item.name }}
      </router-link>
    </template>

    <template #tfoot-type>Total for assets</template>

    <!-- Cash / TOTAL footer rows: one cell per *visible* leaf column, so the
         rows stay aligned with the table at every column-toggle combination
         without any hardcoded colspan. -->
    <template #tfoot-extra="{ flattenedHeaders: flatHeaders }">
      <tr>
        <td
          v-for="header in flatHeaders"
          :key="`cash-${header.key}`"
          class="text-end"
        >
          <span v-if="header.key === 'type'" class="text-start">Cash</span>
          <template v-else-if="header.key === 'current_value'">{{
            totals.cash
          }}</template>
          <span
            v-else-if="header.key === 'share_of_portfolio'"
            class="font-italic"
            >{{ totals.cash_share_of_portfolio }}</span
          >
        </td>
      </tr>
      <tr class="font-weight-bold">
        <td
          v-for="header in flatHeaders"
          :key="`total-${header.key}`"
          class="text-end"
        >
          <span v-if="header.key === 'type'" class="text-start">TOTAL</span>
          <template v-else-if="header.key === 'current_value'">{{
            totals.total_nav
          }}</template>
          <span v-else-if="header.key === 'irr'" class="font-italic">{{
            totals.irr
          }}</span>
        </td>
      </tr>
    </template>
  </PositionsPageBase>
</template>

<script setup>
import { ref } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getOpenPositions } from '@/services/api'
import {
  openPositionsHeaders,
  openPercentageColumns,
  openDefaultVisibleKeys,
} from '@/config/positionsHeaders'

const totals = ref({})
const cashBalances = ref({})
const cashBalancesLoading = ref(true)

const percentageColumns = openPercentageColumns

const fetchOpenPositions = async ({
  dateFrom,
  dateTo,
  page,
  itemsPerPage,
  search,
  sortBy,
}) => {
  cashBalancesLoading.value = true
  try {
    const data = await getOpenPositions(
      dateFrom,
      dateTo,
      page,
      itemsPerPage,
      search,
      sortBy
    )
    totals.value = data.portfolio_open_totals
    cashBalances.value = data.cash_balances
    return {
      positions: data.portfolio_open,
      totals: data.portfolio_open_totals,
      total_items: data.total_items,
    }
  } finally {
    cashBalancesLoading.value = false
  }
}
</script>

<style scoped>
.v-card-title {
  font-size: 1rem;
}
</style>
