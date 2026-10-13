<template>
  <!-- Exact security history table (C4): every observation under its server
       period key — same-date events stay separate rows — with exact displays
       and explicit status/reason/knownSubtotal text. Carry-forward endpoints
       never appear here: the table lists observed points only. Text
       interpolation only; server strings can never inject markup.
       Phase C: collapsed by default behind a labelled disclosure, and the
       accepted document paginates CLIENT-SIDE (no new API fetch, no
       resampling): 25 rows initially with 25/50/100 choices. Pages key on the
       document identity — an incompatible document resets to page 1, a
       shrinking document clamps. Distinct same-date keys stay distinct rows
       because paging slices the server-ordered period list by index. -->
  <!-- data-testid on the outer disclosure marks the mounted modern table
       surface even while collapsed (page-level probes use presence); the
       readable region itself lives inside the disclosure. -->
  <ChartDisclosure
    data-testid="security-data-table"
    show-label="Show exact values by observation"
    hide-label="Hide exact values by observation"
    test-id="security-table-toggle"
  >
    <div class="security-table" role="region" aria-label="Exact chart values by observation" tabindex="0">
      <table>
        <caption>Exact values by observation</caption>
        <thead>
          <tr>
            <th scope="col" class="security-table__date">Date</th>
            <th scope="col" class="security-table__value">{{ seriesLabel }}</th>
            <th scope="col" class="security-table__unit">{{ axisName }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in pageRows"
            :key="row.period.key"
            :data-period-key="row.period.key"
          >
            <th scope="row" class="security-table__date">
              {{ row.period.displayLabel }}
            </th>
            <td class="security-table__value">{{ pointText(document.series[0]?.points[row.index]) }}</td>
            <td class="security-table__unit">{{ axisName }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="total > 0" class="security-table__pagination" data-testid="security-table-pagination">
        <button
          type="button"
          data-testid="security-table-prev"
          aria-label="Previous observations page"
          :disabled="page <= 1"
          @click="page -= 1"
        >
          Previous
        </button>
        <span data-testid="security-table-range">{{ rangeStart }}–{{ rangeEnd }} of {{ total }} observations</span>
        <button
          type="button"
          data-testid="security-table-next"
          aria-label="Next observations page"
          :disabled="page >= pageCount"
          @click="page += 1"
        >
          Next
        </button>
        <label>
          Observations per page
          <select
            data-testid="security-table-page-size"
            :value="pageSize"
            @change="pageSize = Number(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }}</option>
          </select>
        </label>
      </div>
    </div>
  </ChartDisclosure>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ChartDocument, ChartPeriod, ChartValue } from './contracts'
import { securityAxisName } from './buildSecurityOption'
import ChartDisclosure from './ChartDisclosure.vue'

const props = defineProps<{
  document: ChartDocument
}>()

const PAGE_SIZES = [25, 50, 100] as const
const page = ref(1)
const pageSize = ref<number>(25)

const total = computed(() => props.document.periods.length)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const rangeStart = computed(() => (total.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))

const pageRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return props.document.periods
    .slice(start, start + pageSize.value)
    .map((period: ChartPeriod, index: number) => ({ period, index: start + index }))
})

// An incompatible document (different security/kind) restarts the page; a
// compatible refresh only clamps against the new observation count.
const documentIdentity = computed(() => `${props.document.kind}:${props.document.series[0]?.id ?? ''}`)
watch(documentIdentity, () => {
  page.value = 1
})
watch([total, pageSize], () => {
  if (page.value > pageCount.value) page.value = pageCount.value
})

const seriesLabel = computed(() => props.document.series[0]?.label ?? '')
const axisName = computed(() => securityAxisName(props.document))

function pointText(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? ` (known subtotal ${point.knownSubtotal})` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}
</script>

<style scoped>
.security-table {
  overflow-x: auto;
  max-width: 100%;
}

table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.875rem;
}

caption {
  text-align: left;
  font-weight: 600;
  padding: 8px 0;
  color: #172b4d;
}

th,
td {
  border-bottom: 1px solid #e2e6eb;
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
}

.security-table__date {
  font-weight: 600;
}

.security-table__value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.security-table__unit {
  color: #5c6b7a;
  font-size: 0.8125rem;
}

.security-table__pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 0.8125rem;
  color: #526477;
}

.security-table__pagination button {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 32px;
  padding: 4px 10px;
  cursor: pointer;
}

.security-table__pagination button:disabled {
  color: #98a4b3;
  cursor: default;
}

.security-table__pagination select {
  min-height: 32px;
  border: 1px solid rgba(23, 43, 77, 0.24);
  border-radius: 4px;
  background: #fff;
  padding: 2px 6px;
}

.security-table__pagination button:focus-visible,
.security-table__pagination select:focus-visible {
  outline: 2px solid #0f4c81;
  outline-offset: 2px;
}
</style>
