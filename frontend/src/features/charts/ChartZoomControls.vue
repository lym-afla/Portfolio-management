<template>
  <!-- Phase C: the inspection card is gone; these are the retained zoom
       controls — native selects are the keyboard path for the view-only
       viewport (the canvas slider is pointer-driven), plus Reset zoom.
       Zoom changes only the viewport — never queries, values or IRR
       horizons. -->
  <div class="chart-zoom" role="group" aria-label="Chart viewport" data-testid="chart-zoom-controls">
    <label>
      Start period
      <select data-testid="chart-zoom-start" :value="interaction.viewport?.firstPeriodKey ?? firstKey" @change="setViewport('first', ($event.target as HTMLSelectElement).value)">
        <option v-for="period in document.periods" :key="period.key" :value="period.key">
          {{ period.displayLabel }}
        </option>
      </select>
    </label>
    <label>
      End period
      <select data-testid="chart-zoom-end" :value="interaction.viewport?.lastPeriodKey ?? lastKey" @change="setViewport('last', ($event.target as HTMLSelectElement).value)">
        <option v-for="period in document.periods" :key="period.key" :value="period.key">
          {{ period.displayLabel }}
        </option>
      </select>
    </label>
    <button type="button" class="chart-zoom__reset" data-testid="chart-zoom-reset" @click="resetZoom">Reset zoom</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChartDocument } from './contracts'
import type { ChartInteraction } from './interaction'

const props = defineProps<{
  document: ChartDocument
  interaction: ChartInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: ChartInteraction): void
}>()

const firstKey = computed(() => props.document.periods[0]?.key ?? '')
const lastKey = computed(() => props.document.periods[props.document.periods.length - 1]?.key ?? '')

function orderedViewport(first: string, last: string) {
  const keys = props.document.periods.map((period) => period.key)
  const firstIndex = keys.indexOf(first)
  const lastIndex = keys.indexOf(last)
  if (firstIndex < 0 || lastIndex < 0) return null
  // Validate ordered keys: a reversed pick swaps instead of inventing order.
  return firstIndex <= lastIndex
    ? { firstPeriodKey: first, lastPeriodKey: last }
    : { firstPeriodKey: last, lastPeriodKey: first }
}

function setViewport(edge: 'first' | 'last', key: string): void {
  const current = props.interaction.viewport ?? { firstPeriodKey: firstKey.value, lastPeriodKey: lastKey.value }
  const raw = edge === 'first' ? { firstPeriodKey: key, lastPeriodKey: current.lastPeriodKey } : { firstPeriodKey: current.firstPeriodKey, lastPeriodKey: key }
  const viewport = orderedViewport(raw.firstPeriodKey, raw.lastPeriodKey)
  if (viewport) emit('update:interaction', { ...props.interaction, viewport })
}

function resetZoom(): void {
  emit('update:interaction', { ...props.interaction, viewport: null })
}
</script>

<style scoped>
.chart-zoom {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
}

.chart-zoom label {
  display: grid;
  gap: 4px;
  font-size: 0.8125rem;
  color: #526477;
}

.chart-zoom select {
  min-height: 36px;
  border: 1px solid rgba(23, 43, 77, 0.24);
  border-radius: 4px;
  background: #fff;
  padding: 4px 8px;
}

.chart-zoom__reset {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}

.chart-zoom__reset:focus-visible,
.chart-zoom select:focus-visible {
  outline: 2px solid #0f4c81;
  outline-offset: 2px;
}
</style>
