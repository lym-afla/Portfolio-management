<template>
  <PositionsPageBase
    :fetch-positions="fetchClosedPositions"
    :headers="headers"
    page-title="Closed Positions"
  >

    <template #[`item.investment_date`]="{ item }">
      {{ formatDate(item.investment_date) }}
    </template>

    <template #[`item.exit_date`]="{ item }">
      {{ formatDate(item.exit_date) }}
    </template>

    <template #header="{ header }">
      <span>{{ header.value }}</span>
      <v-icon v-if="header.sortable" size="small" class="ml-1">{{ getSortIcon(header.key) }}</v-icon>
    </template>

    <template v-for="key in percentageColumns" :key="key" #[`item.${key}`]="{ item }">
      <span v-if="item && item[key] !== undefined" class="font-italic">{{ item[key] }}</span>
      <span v-else>-</span>
    </template>

    <template #tfoot>
      <tfoot>
        <tr class="font-weight-bold">
          <td v-for="header in flattenedHeaders" :key="header.key" :class="['text-' + header.align, header.key === 'type' ? 'start' : '']">
            <template v-if="header.key === 'type'">
              TOTAL
            </template>
            <template v-else-if="percentageColumns.includes(header.key)">
              <span class="font-italic">{{ totals[header.key] }}</span>
            </template>
            <template v-else>
              {{ totals[header.key] }}
            </template>
          </td>
        </tr>
      </tfoot>
    </template>
  </PositionsPageBase>
</template>

<script>
import { ref, computed, watch } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getClosedPositions } from '@/services/api'
import { formatDate } from '@/utils/formatters'
import { useStore } from 'vuex'

export default {
  name: 'ClosedPositions',
  components: {
    PositionsPageBase,
  },
  setup() {
    const store = useStore()
    const totals = ref({})

    const headers = ref([
      { title: 'Type', key: 'type', align: 'start', sortable: true },
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Currency', key: 'currency', align: 'center', sortable: true },
      // { title: 'Max position', key: 'max_position', align: 'center', sortable: true },
      {
        title: 'Entry',
        key: 'entry',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Date', key: 'investment_date', align: 'center', sortable: true },
          { title: 'Value', key: 'entry_value', align: 'center', sortable: true },
        ],
      },
      {
        title: 'Exit',
        key: 'exit',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Date', key: 'exit_date', align: 'center', sortable: true },
          { title: 'Value', key: 'exit_value', align: 'center', sortable: true },
        ],
      },
      {
        title: 'Realized gain/(loss)',
        key: 'realized',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'realized_gl', align: 'center', sortable: true },
          { title: '%', key: 'price_change_percentage', align: 'center', class: 'font-italic', sortable: true },
        ],
      },
      {
        title: 'Capital distribution',
        key: 'capital',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'capital_distribution', align: 'center', sortable: true },
          { title: '%', key: 'capital_distribution_percentage', align: 'center', class: 'font-italic', sortable: true },
        ],
      },
      {
        title: 'Commission',
        key: 'commission',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'commission', align: 'center', sortable: true },
          { title: '%', key: 'commission_percentage', align: 'center', class: 'font-italic', sortable: true },
        ],
      },
      {
        title: 'Total return',
        key: 'total',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'total_return_amount', align: 'center', sortable: true },
          { title: '%', key: 'total_return_percentage', align: 'center', class: 'font-italic', sortable: true },
          { title: 'IRR', key: 'irr', align: 'center', class: 'font-italic', sortable: true },
        ],
      },
    ])

    const percentageColumns = [
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr'
    ]

    const fetchClosedPositions = async (timespan, page, itemsPerPage, search, sortBy) => {
      const data = await getClosedPositions(timespan, page, itemsPerPage, search, sortBy)
      totals.value = data.portfolio_closed_totals
      return {
        positions: data.portfolio_closed,
        total_items: data.total_items,
      }
    }

    const flattenedHeaders = computed(() => {
      return headers.value.flatMap(header => 
        header.children 
          ? header.children
          : header
      );
    });

    const refreshData = () => {
      // Implement your refresh logic here
      // This might involve calling fetchClosedPositions again
    }

    watch(() => store.state.dataRefreshTrigger, refreshData)

    return {
      headers,
      percentageColumns,
      fetchClosedPositions,
      formatDate,
      totals,
      flattenedHeaders,
    }
  }
}
</script>