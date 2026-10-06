<template>
  <!-- The security histories' only ECharts runtime import (lazy, C4).
       vue-echarts owns initialization/disposal — we never dispose its chart
       ourselves. Zoom is view-only: dataZoom events normalize to the last
       entry and are emitted as server period keys without event loops. -->
  <div ref="host" class="echarts-security">
    <VChart
      class="echarts-security__chart"
      :option="option"
      :update-options="{ notMerge: true }"
      autoresize
      @datazoom="onDataZoom"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  AriaComponent,
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'
import type { ChartDocument } from './contracts'
import type { SecurityInteraction } from './securityInteraction'
import { reconcileSecurityInteraction } from './securityInteraction'
import { buildSecurityOption } from './buildSecurityOption'

use([
  LineChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  DataZoomComponent,
  AriaComponent,
  CanvasRenderer,
])

const props = defineProps<{
  document: ChartDocument
  interaction: SecurityInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: SecurityInteraction): void
  (e: 'render-error', error: Error): void
}>()

const host = ref<HTMLElement | null>(null)
let disposed = false

onUnmounted(() => {
  disposed = true
})

const option = computed<EChartsOption>(() => {
  try {
    return buildSecurityOption(props.document, props.interaction, () => host.value)
  } catch (error) {
    // Option construction failures (e.g. out-of-range plot values) are
    // recoverable rendering failures, never empty-success charts.
    if (!disposed) emit('render-error', error instanceof Error ? error : new Error(String(error)))
    return { series: [] }
  }
})

function onDataZoom(params: unknown): void {
  // Wheel/pinch on the inside zoom arrives as a batched event; slider and
  // programmatic changes arrive flat. Normalize to the last dataZoom entry.
  const event = params as { start?: unknown; end?: unknown; batch?: Array<{ componentType?: string; start?: unknown; end?: unknown }> }
  const entries = Array.isArray(event.batch) ? event.batch.filter((entry) => entry.componentType !== 'toolbox') : [event]
  const last = entries[entries.length - 1]
  if (!last) return
  const start = typeof last.start === 'number' ? last.start : undefined
  const end = typeof last.end === 'number' ? last.end : undefined
  const { periods } = props.document
  if (periods.length === 0 || start === undefined || end === undefined) return
  const lastIndex = periods.length - 1
  const firstIndex = Math.min(lastIndex, Math.max(0, Math.round((start / 100) * lastIndex)))
  const endIndex = Math.min(lastIndex, Math.max(firstIndex, Math.round((end / 100) * lastIndex)))
  const viewport = { firstPeriodKey: periods[firstIndex].key, lastPeriodKey: periods[endIndex].key }
  const next = reconcileSecurityInteraction(props.document, props.document, { viewport })
  if (
    next.viewport &&
    (next.viewport.firstPeriodKey !== props.interaction.viewport?.firstPeriodKey ||
      next.viewport.lastPeriodKey !== props.interaction.viewport?.lastPeriodKey)
  ) {
    if (!disposed) emit('update:interaction', next)
  }
}
</script>

<style scoped>
.echarts-security {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.echarts-security__chart {
  width: 100%;
  height: 100%;
}
</style>
