<template>
  <!-- Exact allocation table (C4): every server row in rank order — signed,
       zero, partial and unavailable rows included, never abs()-ed, suppressed
       or renormalized — with the backend-supplied full-NAV denominator and
       total share. The total percentage appears only when the backend
       certifies one; there is no hardcoded 100% on the modern path. Text
       interpolation only: server strings can never inject markup. -->
  <div class="allocation-table" role="region" aria-label="Exact allocation values" tabindex="0" data-testid="allocation-data-table">
    <table>
      <caption>Exact allocation by {{ dimensionLabel }}</caption>
      <thead>
        <tr>
          <th scope="col" class="allocation-table__category">Category</th>
          <th scope="col" class="allocation-table__value">{{ currency }} amount</th>
          <th scope="col" class="allocation-table__value">Share</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="allocation in document.allocations"
          :key="allocation.seriesId"
          :class="{ 'allocation-table__row--focused': interaction.focusedSeriesId === allocation.seriesId }"
          tabindex="0"
          :aria-selected="interaction.focusedSeriesId === allocation.seriesId"
          :data-allocation-row="allocation.seriesId"
          @click="focus(allocation.seriesId)"
          @keydown.enter.prevent="focus(allocation.seriesId)"
          @keydown.space.prevent="focus(allocation.seriesId)"
        >
          <th scope="row" class="allocation-table__category">{{ label(allocation.seriesId) }}</th>
          <td class="allocation-table__value">{{ valueText(allocation.amount) }}</td>
          <td class="allocation-table__value">{{ valueText(allocation.share) }}</td>
        </tr>
        <tr class="allocation-table__total">
          <th scope="row" class="allocation-table__category">Total (full NAV)</th>
          <td class="allocation-table__value">{{ valueText(document.allocationSummary?.denominator) }}</td>
          <td class="allocation-table__value">{{ valueText(document.allocationSummary?.totalShare) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChartDocument, ChartValue } from './contracts'
import type { AllocationInteraction } from './allocationInteraction'

const props = defineProps<{
  document: ChartDocument
  interaction: AllocationInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: AllocationInteraction): void
}>()

const DIMENSION_LABELS: Record<string, string> = {
  asset_type: 'asset type',
  asset_class: 'asset class',
  currency: 'currency',
}

const dimensionLabel = computed(() => DIMENSION_LABELS[props.document.allocationSummary?.dimension ?? ''] ?? 'category')
const currency = computed(() => {
  const unit = props.document.allocationSummary?.unit
  return unit?.kind === 'money' ? unit.currency : ''
})

function label(seriesId: string): string {
  return props.document.series.find((series) => series.id === seriesId)?.label ?? seriesId
}

function valueText(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? ` (known subtotal ${point.knownSubtotal})` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}

function focus(seriesId: string): void {
  emit('update:interaction', { focusedSeriesId: seriesId })
}
</script>

<style scoped>
.allocation-table {
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

.allocation-table__category {
  font-weight: 600;
}

.allocation-table__value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.allocation-table__total th,
.allocation-table__total td {
  font-weight: 700;
  border-top: 2px solid #172b4d;
}

.allocation-table__row--focused,
.allocation-table__row:focus-visible {
  background: #f2f4f7;
  outline: 2px solid #0f4c81;
  outline-offset: -2px;
}
</style>
