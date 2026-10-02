<template>
  <!-- Shared pointer/keyboard inspection of one server period plus the native
       viewport controls. All text is Vue-interpolated server data; actual
       units and horizons are shown (first interval is inception). Zoom
       changes only the viewport — never queries, values or IRR horizons. -->
  <section class="chart-inspection" aria-label="Chart inspection">
    <h3 class="chart-inspection__heading">Inspection</h3>
    <p v-if="!inspectedPeriod" class="chart-inspection__empty">
      Select a table row or point at the chart to inspect a period.
    </p>
    <dl v-else class="chart-inspection__details">
      <div>
        <dt>Period</dt>
        <dd>{{ inspectedPeriod.displayLabel }} ({{ inspectedPeriod.endDate }})</dd>
      </div>
      <div>
        <dt>Horizon</dt>
        <dd>{{ horizonText(inspectedPeriod) }}</dd>
      </div>
      <div v-for="entry in inspectedValues" :key="entry.id">
        <dt>{{ entry.label }}</dt>
        <dd>{{ entry.display }} <span class="chart-inspection__unit">{{ entry.unit }}</span></dd>
      </div>
      <div v-if="total">
        <dt>Portfolio NAV (all categories)</dt>
        <dd>{{ total.display }}</dd>
      </div>
    </dl>

    <div class="chart-inspection__viewport" role="group" aria-label="Chart viewport">
      <label>
        Start period
        <select :value="interaction.viewport?.firstPeriodKey ?? firstKey" @change="setViewport('first', ($event.target as HTMLSelectElement).value)">
          <option v-for="period in document.periods" :key="period.key" :value="period.key">
            {{ period.displayLabel }}
          </option>
        </select>
      </label>
      <label>
        End period
        <select :value="interaction.viewport?.lastPeriodKey ?? lastKey" @change="setViewport('last', ($event.target as HTMLSelectElement).value)">
          <option v-for="period in document.periods" :key="period.key" :value="period.key">
            {{ period.displayLabel }}
          </option>
        </select>
      </label>
      <button type="button" class="chart-inspection__reset" @click="resetZoom">Reset zoom</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChartDocument, ChartPeriod } from './contracts'
import type { ChartInteraction } from './interaction'

const props = defineProps<{
  document: ChartDocument
  interaction: ChartInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: ChartInteraction): void
}>()

const inspectedPeriod = computed<ChartPeriod | null>(() =>
  props.document.periods.find((period) => period.key === props.interaction.inspectedPeriodKey) ?? null,
)

const firstKey = computed(() => props.document.periods[0]?.key ?? '')
const lastKey = computed(() => props.document.periods[props.document.periods.length - 1]?.key ?? '')

const inspectedValues = computed(() => {
  if (!inspectedPeriod.value) return []
  const index = props.document.periods.findIndex((period) => period.key === inspectedPeriod.value!.key)
  const visible = new Set(props.interaction.visibleSeriesIds)
  return props.document.series
    .filter((series) => visible.has(series.id))
    .map((series) => ({
      id: series.id,
      label: series.label,
      display: series.points[index]?.display ?? '–',
      unit: unitText(series.unit.kind, series.unit.kind === 'money' ? series.unit.currency : undefined),
    }))
})

const total = computed(() => {
  if (!inspectedPeriod.value) return null
  const index = props.document.periods.findIndex((period) => period.key === inspectedPeriod.value!.key)
  return props.document.totals?.[index] ?? null
})

function unitText(kind: string, currency?: string): string {
  if (kind === 'money') return `reporting currency ${currency ?? ''}`.trim()
  if (kind === 'ratio') return 'raw ratio'
  if (kind === 'percent_of_nominal') return '% of nominal'
  return 'quantity'
}

function horizonText(period: ChartPeriod): string {
  if (period.interval.kind === 'inception') return `Inception to ${period.interval.endDate}`
  return `${period.interval.startDate} – ${period.interval.endDate}`
}

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
.chart-inspection {
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  padding: 12px;
  display: grid;
  gap: 10px;
  font-size: 0.875rem;
}

.chart-inspection__heading {
  font-size: 1rem;
  margin: 0;
}

.chart-inspection__empty {
  margin: 0;
  color: #526477;
}

.chart-inspection__details {
  display: grid;
  gap: 4px;
  margin: 0;
}

.chart-inspection__details dt {
  font-weight: 600;
  color: #526477;
}

.chart-inspection__details dd {
  margin: 0 0 6px;
}

.chart-inspection__unit {
  color: #526477;
  font-size: 0.75rem;
}

.chart-inspection__viewport {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
}

.chart-inspection__viewport label {
  display: grid;
  gap: 4px;
  font-size: 0.8125rem;
  color: #526477;
}

.chart-inspection__reset {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>
