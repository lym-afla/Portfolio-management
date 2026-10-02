<template>
  <!-- Exact-value alternative: caption, scoped headers, sticky period identity
       and right-aligned tabular values. Every series column shows the exact
       server display; unavailable/partial points state their status, reason
       and knownSubtotal as explicitly incomplete information. The full-NAV
       column comes only from document.totals and ignores hidden categories.
       Text interpolation only — server names can never inject markup. -->
  <div class="chart-table" role="region" aria-label="Exact chart values by period" tabindex="0">
    <table>
      <caption>Exact values by period</caption>
      <thead>
        <tr>
          <th scope="col" class="chart-table__period">Period</th>
          <th scope="col">Interval</th>
          <th v-for="series in document.series" :key="series.id" scope="col" class="chart-table__value">
            {{ series.label }}
          </th>
          <th v-if="hasTotals" scope="col" class="chart-table__value">Portfolio NAV (all categories)</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(period, index) in document.periods"
          :key="period.key"
          :class="{ 'chart-table__row--inspected': interaction.inspectedPeriodKey === period.key }"
          tabindex="0"
          :aria-selected="interaction.inspectedPeriodKey === period.key"
          @click="inspect(period.key)"
          @keydown.enter.prevent="inspect(period.key)"
          @keydown.space.prevent="inspect(period.key)"
        >
          <th scope="row" class="chart-table__period">
            {{ period.displayLabel }}
            <span v-if="period.partialPeriod" class="chart-table__partial">partial calendar period</span>
          </th>
          <td>{{ intervalLabel(period) }}</td>
          <td v-for="series in document.series" :key="series.id" class="chart-table__value">
            {{ pointText(series.points[index]) }}
          </td>
          <td v-if="hasTotals" class="chart-table__value">
            {{ pointText(document.totals![index]) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChartDocument, ChartPeriod, ChartValue } from './contracts'
import type { ChartInteraction } from './interaction'

const props = defineProps<{
  document: ChartDocument
  interaction: ChartInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: ChartInteraction): void
}>()

const hasTotals = computed(() => (props.document.totals?.length ?? 0) === props.document.periods.length)

function inspect(key: string): void {
  emit('update:interaction', { ...props.interaction, inspectedPeriodKey: key })
}

function intervalLabel(period: ChartPeriod): string {
  if (period.interval.kind === 'inception') {
    return `Inception to ${period.interval.endDate}`
  }
  return `${period.interval.startDate} – ${period.interval.endDate}`
}

function pointText(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? ` (known subtotal ${point.knownSubtotal})` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}
</script>

<style scoped>
.chart-table {
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

.chart-table__period {
  position: sticky;
  left: 0;
  background: #fff;
  z-index: 1;
  font-weight: 600;
}

.chart-table__value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.chart-table__partial {
  display: block;
  font-size: 0.75rem;
  color: #9a6700;
  font-weight: 400;
}

.chart-table__row--inspected {
  background: #f2f4f7;
}

tbody tr:focus-visible {
  outline: 2px solid #0f4c81;
  outline-offset: -2px;
}
</style>
