<template>
  <!-- The allocation pie's only ECharts runtime import (lazy-loaded, C4).
       vue-echarts owns initialization/disposal — we never dispose its chart
       ourselves. Narrowly registered modules; the HTML legend's focus is
       dispatched as a transient highlight that cannot change any angle. -->
  <div ref="host" class="echarts-allocation">
    <VChart
      ref="chart"
      class="echarts-allocation__chart"
      :option="option"
      :update-options="{ notMerge: true }"
      autoresize
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { AriaComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'
import type { ChartDocument } from './contracts'
import type { AllocationInteraction } from './allocationInteraction'
import { buildAllocationOption } from './buildAllocationOption'

use([
  PieChart,
  TooltipComponent,
  AriaComponent,
  CanvasRenderer,
])

const props = defineProps<{
  document: ChartDocument
  interaction: AllocationInteraction
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: AllocationInteraction): void
  (e: 'render-error', error: Error): void
}>()

const host = ref<HTMLElement | null>(null)
// The wrapper exposes the ECharts instance; highlight/downplay are the only
// actions we dispatch, and a disposed instance is never touched.
const chart = ref<{ dispatchAction: (payload: Record<string, unknown>) => void } | null>(null)

const option = computed<EChartsOption>(() => {
  try {
    return buildAllocationOption(props.document, () => host.value) ?? { series: [] }
  } catch (error) {
    // Option construction failures (e.g. out-of-range plot values) are
    // recoverable rendering failures, never empty-success charts.
    emit('render-error', error instanceof Error ? error : new Error(String(error)))
    return { series: [] }
  }
})

// Focus tracking: highlight the focused slice, downplay the previous one.
// A no-op when the instance is gone (disposed or never mounted).
watch(
  () => props.interaction.focusedSeriesId,
  (next, previous) => {
    const instance = chart.value
    if (!instance) return
    const index = props.document.allocations?.findIndex((allocation) => allocation.seriesId === previous) ?? -1
    if (previous && previous !== next && index >= 0) {
      instance.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: index })
    }
    const nextIndex = props.document.allocations?.findIndex((allocation) => allocation.seriesId === next) ?? -1
    if (next && nextIndex >= 0) {
      instance.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: nextIndex })
    }
  },
)

defineExpose({
  dispatchAction: (payload: Record<string, unknown>) => chart.value?.dispatchAction(payload),
})
</script>

<style scoped>
.echarts-allocation {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 280px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.echarts-allocation__chart {
  width: 100%;
  height: 100%;
}
</style>
