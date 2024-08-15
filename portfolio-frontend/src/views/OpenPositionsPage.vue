<template>
  <PositionsPageBase
    :fetch-positions="fetchOpenPositions"
    :headers="headers"
    page-title="Open Positions"
  >
    <template #[`item.investment_date`]="{ item }">
      {{ formatDate(item.investment_date) }}
    </template>

    <template v-for="key in percentageColumns" :key="key" #[`item.${key}`]="{ item }">
      <span v-if="item && item[key] !== undefined" class="font-italic">{{ item[key] }}</span>
      <span v-else>-</span>
    </template>

    <template #bottom>
      <v-row class="mt-2">
        <v-col>
          <strong>TOTAL:</strong>
          <!-- Add your totals here -->
        </v-col>
      </v-row>
    </template>
  </PositionsPageBase>
</template>

<script>
import { ref } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getOpenPositions } from '@/services/api'
import { formatDate } from '@/utils/formatters'

export default {
  name: 'OpenPositions',
  components: {
    PositionsPageBase,
  },
  setup() {
    const headers = ref([
      { title: 'Type', key: 'type', align: 'start', sortable: true },
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Currency', key: 'currency', align: 'center', sortable: true },
      { title: 'Investment Date', key: 'investment_date', align: 'center', sortable: true },
      // Add other headers as needed
    ])

    const percentageColumns = [
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr'
    ]

    const fetchOpenPositions = async (timespan, page, itemsPerPage, search, sortBy) => {
      const data = await getOpenPositions(timespan, page, itemsPerPage, search, sortBy)
      return {
        positions: data.portfolio_open,
        totals: data.portfolio_open_totals,
        total_items: data.total_items,
      }
    }

    return {
      headers,
      percentageColumns,
      fetchOpenPositions,
      formatDate,
    }
  }
}
</script>
