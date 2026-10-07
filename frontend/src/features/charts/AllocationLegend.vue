<template>
  <!-- Allocation legend (C4): HTML buttons that HIGHLIGHT and FOCUS a slice
       and its table row. They never hide categories or dispatch a selection
       that renormalizes pie geometry — the only interaction state is which
       allocation holds the focus, and every button announces the exact
       server amount and share. -->
  <div class="allocation-legend" role="group" aria-label="Allocation slices" data-testid="allocation-legend">
    <button
      v-for="allocation in document.allocations"
      :key="allocation.seriesId"
      type="button"
      class="allocation-legend__button"
      :data-allocation-id="allocation.seriesId"
      :aria-label="`${label(allocation.seriesId)}: ${amountText(allocation)}, share ${shareText(allocation)}`"
      :class="{ 'allocation-legend__button--focused': interaction.focusedSeriesId === allocation.seriesId }"
      @click="focus(allocation.seriesId)"
      @focus="focus(allocation.seriesId)"
      @blur="clear"
      @mouseenter="focus(allocation.seriesId)"
      @mouseleave="clear"
    >
      <span
        aria-hidden="true"
        class="allocation-legend__swatch"
        :style="{ background: seriesColor(allocation.seriesId) }"
      />
      {{ label(allocation.seriesId) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import type { ChartAllocation, ChartDocument } from './contracts'
import { seriesColor } from './seriesStyles'
import type { AllocationInteraction } from './allocationInteraction'

const props = defineProps<{
  document: ChartDocument
  interaction: AllocationInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: AllocationInteraction): void
}>()

function label(seriesId: string): string {
  return props.document.series.find((series) => series.id === seriesId)?.label ?? seriesId
}

function amountText(allocation: ChartAllocation): string {
  return allocation.amount.status === 'ok' ? allocation.amount.display : `${allocation.amount.display} (${allocation.amount.status})`
}

function shareText(allocation: ChartAllocation): string {
  return allocation.share.status === 'ok' ? allocation.share.display : `${allocation.share.display} (${allocation.share.status})`
}

function focus(seriesId: string): void {
  emit('update:interaction', { focusedSeriesId: seriesId })
}

function clear(): void {
  emit('update:interaction', { focusedSeriesId: null })
}
</script>

<style scoped>
.allocation-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}

.allocation-legend__button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  padding: 4px 10px;
  min-height: 32px;
  cursor: pointer;
  font-size: 0.875rem;
  color: #172b4d;
}

.allocation-legend__button--focused,
.allocation-legend__button:focus-visible {
  border-color: #0f4c81;
  box-shadow: inset 0 0 0 1px #0f4c81;
  outline: none;
}

.allocation-legend__swatch {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  display: inline-block;
}
</style>
