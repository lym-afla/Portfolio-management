<template>
  <PositionsPageBase
    :fetch-positions="fetchClosedPositions"
    :headers="closedPositionsHeaders"
    page-title="Closed Positions"
  >
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

    <template #tfoot-type>TOTAL</template>
    <template
      v-for="key in percentageColumns"
      :key="`tfoot-${key}`"
      #[`tfoot-${key}`]
    >
      <span class="font-italic">{{ totals[key] }}</span>
    </template>
  </PositionsPageBase>
</template>

<script setup>
import { ref } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getClosedPositions } from '@/services/api'
import {
  closedPositionsHeaders,
  closedPercentageColumns,
} from '@/config/positionsHeaders'

const totals = ref({})

const percentageColumns = closedPercentageColumns

const fetchClosedPositions = async ({
  dateFrom,
  dateTo,
  page,
  itemsPerPage,
  search,
  sortBy,
}) => {
  const data = await getClosedPositions(
    dateFrom,
    dateTo,
    page,
    itemsPerPage,
    search,
    sortBy
  )
  totals.value = data.portfolio_closed_totals
  return {
    positions: data.portfolio_closed,
    totals: data.portfolio_closed_totals,
    total_items: data.total_items,
  }
}
</script>
