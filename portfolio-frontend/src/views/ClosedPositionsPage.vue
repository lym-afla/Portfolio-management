<template>
  <PositionsPageBase
    :fetch-positions="fetchClosedPositions"
    :headers="headers"
    page-title="Closed Positions"
  >
    <template #header="{ header }">
      <span>{{ header.value }} T {{ header.sortable }}</span>
      <v-icon v-if="header.sortable" size="small" class="ml-1">{{
        getSortIcon(header.key)
      }}</v-icon>
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

    <template #tfoot>
      <tfoot>
        <tr class="font-weight-bold">
          <td
            v-for="header in flattenedHeaders"
            :key="header.key"
            :class="[
              'text-' + header.align,
              header.key === 'type' ? 'start' : '',
            ]"
          >
            <template v-if="header.key === 'type'"> TOTAL </template>
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
import { ref, computed } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getClosedPositions } from '@/services/api'

export default {
  name: 'ClosedPositions',
  components: {
    PositionsPageBase,
  },
  setup() {
    const totals = ref({})

    const headers = ref([
      { title: 'Type', key: 'type', align: 'start', sortable: false },
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Currency', key: 'currency', align: 'center', sortable: true },
      {
        title: 'Entry',
        key: 'entry',
        align: 'center',
        sortable: false,
        children: [
          {
            title: 'Date',
            key: 'investment_date',
            align: 'center',
            sortable: true,
          },
          {
            title: 'Value',
            key: 'entry_value',
            align: 'center',
            sortable: true,
          },
        ],
      },
      {
        title: 'Exit',
        key: 'exit',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Date', key: 'exit_date', align: 'center', sortable: true },
          {
            title: 'Value',
            key: 'exit_value',
            align: 'center',
            sortable: true,
          },
        ],
      },
      {
        title: 'Realized gain/(loss)',
        key: 'realized',
        align: 'center',
        sortable: false,
        children: [
          {
            title: 'Amount',
            key: 'realized_gl',
            align: 'center',
            sortable: true,
          },
          {
            title: '%',
            key: 'price_change_percentage',
            align: 'center',
            class: 'font-italic',
            sortable: true,
          },
        ],
      },
      {
        title: 'Capital distribution',
        key: 'capital',
        align: 'center',
        sortable: false,
        children: [
          {
            title: 'Amount',
            key: 'capital_distribution',
            align: 'center',
            sortable: true,
          },
          {
            title: '%',
            key: 'capital_distribution_percentage',
            align: 'center',
            class: 'font-italic',
            sortable: true,
          },
        ],
      },
      {
        title: 'Commission',
        key: 'commission',
        align: 'center',
        sortable: false,
        children: [
          {
            title: 'Amount',
            key: 'commission',
            align: 'center',
            sortable: true,
          },
          {
            title: '%',
            key: 'commission_percentage',
            align: 'center',
            class: 'font-italic',
            sortable: true,
          },
        ],
      },
      {
        title: 'Total return',
        key: 'total',
        align: 'center',
        sortable: false,
        children: [
          {
            title: 'Amount',
            key: 'total_return_amount',
            align: 'center',
            sortable: true,
          },
          {
            title: '%',
            key: 'total_return_percentage',
            align: 'center',
            class: 'font-italic',
            sortable: true,
          },
          {
            title: 'IRR',
            key: 'irr',
            align: 'center',
            class: 'font-italic',
            sortable: true,
          },
        ],
      },
    ])

    const percentageColumns = [
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr',
    ]

    const fetchClosedPositions = async ({
      dateFrom,
      dateTo,
      page,
      itemsPerPage,
      search,
      sortBy,
    }) => {
      console.log('[ClosedPositionsPage] fetchClosedPositions called with:', {
        dateFrom,
        dateTo,
        page,
        itemsPerPage,
        search,
        sortBy,
      })
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
        total_items: data.total_items,
      }
    }

    const flattenedHeaders = computed(() => {
      return headers.value.flatMap((header) =>
        header.children ? header.children : header
      )
    })

    return {
      headers,
      percentageColumns,
      fetchClosedPositions,
      totals,
      flattenedHeaders,
    }
  },
}
</script>
