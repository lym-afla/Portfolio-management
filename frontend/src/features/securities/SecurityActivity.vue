<template>
  <v-row>
    <v-col cols="12">
      <WorkspaceSection heading-id="security-transactions" title="Transaction History">
        <slot name="timeline" />
        <div>
          <v-data-table
            :headers="transactionHeaders"
            :items="view.transactions"
            :loading="loading"
            :items-per-page="view.itemsPerPage"
            disable-sort
          >
            <template #item="{ item }">
              <transaction-row
                :transaction="item"
                :currencies="[]"
                :show-balances="false"
                :show-cash-flow="false"
                :show-single-cash-flow="true"
                :show-broker-account="true"
                :show-actions="false"
              />
            </template>

            <template #bottom>
              <div class="activity-footer d-flex align-center justify-space-between pa-2">
                <v-select
                  :model-value="view.itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="rows-per-page-select mr-4"
                  bg-color="white"
                  @update:model-value="emit('update:itemsPerPage', Number($event))"
                />
                <span class="text-caption activity-range">
                  Showing
                  {{ (view.page - 1) * view.itemsPerPage + 1 }}-{{
                    Math.min(
                      view.page * view.itemsPerPage,
                      view.totalItems,
                    )
                  }}
                  of {{ view.totalItems }} entries
                </span>
                <v-pagination
                  :model-value="view.page"
                  :length="view.pageCount"
                  :total-visible="7"
                  rounded="circle"
                  class="activity-pagination"
                  @update:model-value="emit('update:page', Number($event))"
                />
              </div>
            </template>
          </v-data-table>
        </div>
      </WorkspaceSection>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import TransactionRow from '@/components/transactions/TransactionRow.vue'
import type { SecurityActivityView } from './types'

defineProps<{
  view: SecurityActivityView
  itemsPerPageOptions: readonly number[]
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:page': [page: number]
  'update:itemsPerPage': [itemsPerPage: number]
}>()

const transactionHeaders = [
  { title: 'Date', key: 'date', align: 'start' },
  { title: 'Account', key: 'broker_account', align: 'start' },
  { title: 'Description', key: 'description', align: 'start' },
  { title: 'Type', key: 'type', align: 'center' },
  { title: 'Cash Flow', key: 'cash_flow', align: 'center' },
] as const

defineExpose({
  changePage: (page: number) => emit('update:page', page),
  changeItemsPerPage: (itemsPerPage: number) => emit('update:itemsPerPage', itemsPerPage),
})
</script>

<style scoped>
/* The footer is one flex row on wide screens; below the desktop breakpoint
   the rows-per-page control keeps a usable 150px box while the range label
   and the pagination each take their own full-width line. */
.activity-footer {
  flex-wrap: wrap;
  row-gap: 8px;
}
.activity-footer .rows-per-page-select {
  flex: 0 0 150px;
  min-width: 150px;
}
@media (max-width: 960px) {
  .activity-footer .activity-range {
    flex: 1 1 100%;
    order: 3;
  }
  .activity-footer .activity-pagination {
    flex: 1 1 100%;
    order: 4;
    justify-content: flex-start;
  }
}
</style>
