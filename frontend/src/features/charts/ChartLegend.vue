<template>
  <!-- Native HTML legend: real buttons with aria-pressed, stable id keys, no
       canvas legend competing for visibility state. Every series — including
       each IRR line — toggles independently. -->
  <div class="chart-legend" role="group" aria-label="Chart series visibility">
    <button
      v-for="series in document.series"
      :key="series.id"
      type="button"
      class="chart-legend__button"
      :aria-pressed="isVisible(series.id)"
      :data-series-id="series.id"
      @click="toggle(series.id)"
    >
      <span
        aria-hidden="true"
        class="chart-legend__swatch"
        :class="{ 'chart-legend__swatch--dashed': series.metric === 'irr_interval' }"
        :style="{ background: seriesColor(series.id) }"
      />
      {{ seriesControlName(series) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { seriesColor } from './seriesStyles'
import type { ChartDocument } from './contracts'
import { seriesControlName, type ChartInteraction } from './interaction'

const props = defineProps<{
  document: ChartDocument
  interaction: ChartInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: ChartInteraction): void
}>()


function isVisible(id: string): boolean {
  return props.interaction.visibleSeriesIds.includes(id)
}

function toggle(id: string): void {
  const visible = props.interaction.visibleSeriesIds.includes(id)
    ? props.interaction.visibleSeriesIds.filter((entry) => entry !== id)
    : [...props.interaction.visibleSeriesIds, id]
  emit('update:interaction', { ...props.interaction, visibleSeriesIds: visible })
}
</script>

<style scoped>
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}

/* Phase C: no per-button outline in the resting state — the pressed state is
   a light fill plus a thin inset ring, so the legend reads lighter while the
   toggle state and the keyboard focus ring stay plainly visible. */
.chart-legend__button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 4px;
  padding: 4px 10px;
  min-height: 32px;
  cursor: pointer;
  font-size: 0.875rem;
  color: #526477;
}

.chart-legend__button[aria-pressed='true'] {
  color: #172b4d;
  background: #eef3f8;
  box-shadow: inset 0 0 0 1px #0f4c81;
}

.chart-legend__button:focus-visible {
  outline: 2px solid #0f4c81;
  outline-offset: 2px;
}

.chart-legend__swatch {
  width: 14px;
  height: 3px;
  border-radius: 1px;
  display: inline-block;
}

.chart-legend__swatch--dashed {
  background: repeating-linear-gradient(
    to right,
    #1e7f4f 0 3px,
    transparent 3px 6px
  ) !important;
}
</style>
