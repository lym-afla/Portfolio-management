<template>
  <!-- The only place ECharts runtime code is imported. The selected wrapper
       (vue-echarts) owns initialization/disposal — we never dispose its chart
       ourselves. Narrowly registered modules; controlled state is fed back
       from pointer/zoom events by server period keys without event loops. -->
  <div ref="host" class="echarts-nav">
    <VChart
      class="echarts-nav__chart"
      :option="option"
      :update-options="{ notMerge: true }"
      autoresize
      @click="onPointClick"
      @datazoom="onDataZoom"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
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
import type { ChartInteraction } from './interaction'
import { buildNavOption } from './buildNavOption'

use([
  BarChart,
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
  interaction: ChartInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: ChartInteraction): void
  (e: 'render-error', error: Error): void
}>()

const host = ref<HTMLElement | null>(null)

const option = computed<EChartsOption>(() => {
  try {
    return buildNavOption(props.document, props.interaction)
  } catch (error) {
    // Option construction failures (e.g. out-of-range plot values) are
    // recoverable rendering failures, never empty-success charts.
    emit('render-error', error instanceof Error ? error : new Error(String(error)))
    return { series: [] }
  }
})

function onPointClick(params: { dataIndex?: number }): void {
  const key = props.document.periods[params.dataIndex ?? -1]?.key
  if (key && key !== props.interaction.inspectedPeriodKey) {
    emit('update:interaction', { ...props.interaction, inspectedPeriodKey: key })
  }
}

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
  const current = props.interaction.viewport
  if (!current || current.firstPeriodKey !== viewport.firstPeriodKey || current.lastPeriodKey !== viewport.lastPeriodKey) {
    emit('update:interaction', { ...props.interaction, viewport })
  }
}

// vue-echarts' autoresize uses ResizeObserver where available; keep a window
// resize fallback ourselves and always clean it up on unmount.
let resizeListener: (() => void) | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined' && host.value) {
    observer = new ResizeObserver(() => {
      /* sizing is owned by the wrapper's autoresize */
    })
    observer.observe(host.value)
    return
  }
  resizeListener = () => {
    /* sizing is owned by the wrapper's autoresize */
  }
  window.addEventListener('resize', resizeListener)
})

onUnmounted(() => {
  observer?.disconnect()
  observer = null
  if (resizeListener) {
    window.removeEventListener('resize', resizeListener)
    resizeListener = null
  }
})
</script>

<style scoped>
.echarts-nav {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 360px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.echarts-nav__chart {
  width: 100%;
  height: 100%;
}
</style>
