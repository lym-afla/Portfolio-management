<template>
  <PositionsPageBase
    :fetch-positions="fetchOpenPositions"
    :headers="headers"
    page-title="Open Positions"
  >
    <template #above-table>
      <v-card class="mb-4">
        <v-card-title class="text-h6">Cash Balances</v-card-title>
        <v-card-text>
          <v-table density="compact">
            <thead>
              <tr>
                <th class="text-left">Currency</th>
                <th class="text-right">Balance</th>
              </tr>
            </thead>
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

    <template #[`item.investment_date`]="{ item }">
      {{ formatDate(item.investment_date) }}
    </template>

    <template #header>
      <thead>
        <tr>
          <th
            v-for="header in headers"
            :key="header.key"
            :colspan="getColspan(header)"
            :rowspan="getRowspan(header, 0)"
            :class="['text-' + header.align]"
          >
            {{ header.title }}
          </th>
        </tr>
        <tr>
          <template v-for="header in headers" :key="`level1-${header.key}`">
            <template v-if="header.children">
              <th
                v-for="child in header.children"
                :key="child.key"
                :colspan="getColspan(child)"
                :rowspan="getRowspan(child, 1)"
                :class="['text-' + child.align]"
              >
                {{ child.title }}
              </th>
            </template>
          </template>
        </tr>
        <tr>
          <template v-for="header in headers" :key="`level2-${header.key}`">
            <template v-if="header.children">
              <template v-for="child in header.children" :key="`level2-child-${child.key}`">
                <template v-if="child.children">
                  <th
                    v-for="grandchild in child.children"
                    :key="grandchild.key"
                    :class="['text-' + grandchild.align]"
                  >
                    {{ grandchild.title }}
                  </th>
                </template>
              </template>
            </template>
          </template>
        </tr>
      </thead>
    </template>

    <template v-for="key in percentageColumns" :key="key" #[`item.${key}`]="{ item }">
      <span v-if="item && item[key] !== undefined" class="font-italic">{{ item[key] }}</span>
      <span v-else>-</span>
    </template>

    <template #tfoot>
      <tfoot v-if="totals">
        <tr class="font-weight-bold">
          <template v-for="header in flattenedHeaders" :key="header.key">
            <template v-if="header.key !== 'name'">
              <td v-if="header.key === 'type'" colspan="2">
                Total for assets
              </td>
              <td v-else-if="totals[header.key] === undefined" class="text-center"></td>
              <td v-else-if="percentageColumns.includes(header.key)" class="text-center font-italic font-weight-bold">
                {{ totals[header.key] }}
              </td>
              <td v-else-if="totals[header.key] !== undefined" class="text-center">
                {{ totals[header.key] }}
              </td>
              <td v-else></td>
            </template>
          </template>
        </tr>

        <tr>
          <td colspan="2">Cash</td>
          <td colspan="6"></td>
          <td class="text-center">{{ totals.cash }}</td>
          <td class="text-center font-italic">{{ totals.cash_share_of_portfolio }}</td>
          <td colspan="10"></td>
        </tr>

        <tr class="font-weight-bold">
          <td colspan="2">TOTAL</td>
          <td colspan="6"></td>
          <td class="text-center">{{ totals.total_nav }}</td>
          <td colspan="10"></td>
          <td class="text-center font-italic">{{ totals.irr }}</td>
        </tr>
      </tfoot>
    </template>
  </PositionsPageBase>
</template>

<script>
import { ref, computed } from 'vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { getOpenPositions } from '@/services/api'
import { formatDate } from '@/utils/formatters'

export default {
  name: 'OpenPositions',
  components: {
    PositionsPageBase,
  },
  setup() {
    const totals = ref({})
    const cashBalances = ref({})

    const headers = ref([
      { title: 'Type', key: 'type', align: 'start', sortable: true },
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Currency', key: 'currency', align: 'center', sortable: true },
      { title: 'Position', key: 'current_position', align: 'center', sortable: true },
      {
        title: 'Entry',
        key: 'entry',
        align: 'center',
        sortable: false,
        rowspan: 1,
        colspan: 3,
        children: [
          { title: 'Date', key: 'investment_date', align: 'center', sortable: true, rowspan: 2},
          { title: 'Price', key: 'entry_price', align: 'center', sortable: true, rowspan: 2 },
          { title: 'Value', key: 'entry_value', align: 'center', sortable: true, rowspan: 2 },
        ],
      },
      {
        title: 'Current',
        key: 'current',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Price', key: 'current_price', align: 'center', sortable: true },
          { title: 'Value', key: 'current_value', align: 'center', sortable: true },
          { title: 'Share', key: 'share_of_portfolio', align: 'center', sortable: true },
          {
            title: 'Gain/Loss',
            key: 'gain_loss',
            align: 'center',
            sortable: false,
            children: [
              { title: 'Realized', key: 'realized_gl', align: 'center', sortable: true },
              { title: 'Unrealized', key: 'unrealized_gl', align: 'center', sortable: true },
              { title: '%', key: 'price_change_percentage', align: 'center', class: 'font-italic', sortable: true },
            ],
          },
          {
            title: 'Capital Distribution',
            key: 'capital_distribution',
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
            title: 'Total Return',
            key: 'total',
            align: 'center',
            sortable: false,
            children: [
              { title: 'Amount', key: 'total_return_amount', align: 'center', sortable: true },
              { title: '%', key: 'total_return_percentage', align: 'center', class: 'font-italic', sortable: true },
              { title: 'IRR', key: 'irr', align: 'center', class: 'font-italic', sortable: true },
            ],
          },
        ],
      },
    ])

    const percentageColumns = [
      'share_of_portfolio',
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr',
      'all_assets_share_of_portfolio_percentage'
    ]

    const fetchOpenPositions = async (timespan, page, itemsPerPage, search, sortBy) => {
      const data = await getOpenPositions(timespan, page, itemsPerPage, search, sortBy)
      totals.value = data.portfolio_open_totals
      cashBalances.value = data.cash_balances
      return {
        positions: data.portfolio_open,
        total_items: data.total_items,
      }
    }

    const flattenHeaders = (headers) => {
      return headers.flatMap(header => {
        if (header.children) {
          return flattenHeaders(header.children);
        }
        return header;
      });
    };

    const flattenedHeaders = computed(() => {
      return flattenHeaders(headers.value);
    });

    const getColspan = (header) => {
      if (!header.children) return 1
      return header.children.reduce((acc, child) => acc + getColspan(child), 0)
    }

    const getRowspan = (header, level) => {
      if (!header.children) return 3 - level
      if (level === 1 && !header.children[0].children) return 1
      return 1
    }

    return {
      headers,
      percentageColumns,
      fetchOpenPositions,
      formatDate,
      totals,
      flattenedHeaders,
      getColspan,
      getRowspan,
      cashBalances,
    }
  }
}
</script>

<style scoped>
.v-card-title {
  font-size: 1rem !important;
}

</style>