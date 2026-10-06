<template>
  <!-- Exact security history table (C4): every observation under its server
       period key — same-date events stay separate rows — with exact displays
       and explicit status/reason/knownSubtotal text. Carry-forward endpoints
       never appear here: the table lists observed points only. Text
       interpolation only; server strings can never inject markup. -->
  <div class="security-table" role="region" aria-label="Exact chart values by observation" tabindex="0" data-testid="security-data-table">
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
          v-for="(period, index) in document.periods"
          :key="period.key"
          :data-period-key="period.key"
        >
          <th scope="row" class="security-table__date">
            {{ period.displayLabel }}
          </th>
          <td class="security-table__value">{{ pointText(document.series[0]?.points[index]) }}</td>
          <td class="security-table__unit">{{ axisName }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChartDocument, ChartValue } from './contracts'
import { securityAxisName } from './buildSecurityOption'

const props = defineProps<{
  document: ChartDocument
}>()

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
</style>
