<template>
  <!-- Modern allocation composition (C4): the solid pie plus its HTML legend
       for eligible documents; the server-certified reason (no misleading
       pie) for ineligible ones. Rendering failures are recoverable with an
       explicit retry or the explicit user-chosen legacy fallback (the
       incumbent Chart.js bars, supplied through the fallback slot) backed by
       the same accepted result — data errors never reach this component. -->
  <div class="allocation-chart">
    <template v-if="requested && eligible && !fallbackActive">
      <EChartsAllocation
        v-if="!failure"
        :key="mountKey"
        :document="document"
        :interaction="interaction"
        @update:interaction="forward"
        @render-error="onRenderError"
      />
      <div v-if="failure" class="allocation-chart__failure" data-testid="allocation-render-error" role="alert">
        <p>The pie chart could not be drawn: {{ failure.message }}</p>
        <div class="allocation-chart__failure-actions">
          <button type="button" data-testid="allocation-render-retry" @click="retry">Retry chart</button>
          <button type="button" data-testid="allocation-render-fallback" @click="useFallback">Use previous chart</button>
        </div>
      </div>
      <AllocationLegend
        v-if="!failure"
        :document="document"
        :interaction="interaction"
        @update:interaction="forward"
      />
    </template>
    <template v-else-if="requested && !eligible">
      <div class="allocation-chart__reason" data-testid="allocation-ineligible" role="status">
        {{ reason }}
      </div>
    </template>
    <slot v-else name="fallback" />
  </div>
</template>

<script setup lang="ts">
import { computed, onErrorCaptured, onUnmounted, ref } from 'vue'
import type { ChartDocument } from './contracts'
import type { AllocationInteraction } from './allocationInteraction'
import { allocationEligible, allocationIneligibilityReason } from './buildAllocationOption'
import { lazyChartRenderer } from './lazyRenderer'
import AllocationLegend from './AllocationLegend.vue'

// A rejected ECharts chunk download lands in the same recoverable failure
// UI as a render error (explicit retry and user-chosen legacy fallback).
const {
  component: EChartsAllocation,
  retry: retryRendererChunk,
} = lazyChartRenderer(() => import('./EChartsAllocation.vue'), {
  onLoadError: (error) => {
    if (!disposed) failure.value = error
  },
})

const props = defineProps<{
  document: ChartDocument
  interaction: AllocationInteraction
  requested: boolean
}>()

const emit = defineEmits<{
  (e: 'update:interaction', interaction: AllocationInteraction): void
}>()

const failure = ref<Error | null>(null)
const fallbackActive = ref(false)
const mountKey = ref(0)
let disposed = false

onUnmounted(() => {
  disposed = true
})

const eligible = computed(() => allocationEligible(props.document))
const reason = computed(() => allocationIneligibilityReason(props.document))

onErrorCaptured((error) => {
  // Rendering failures inside the lazy subtree stop here; a dead instance
  // can never mutate state after disposal.
  if (!disposed) failure.value = error instanceof Error ? error : new Error(String(error))
  return false
})

function onRenderError(error: Error): void {
  if (!disposed) failure.value = error
}

function retry(): void {
  if (disposed) return
  failure.value = null
  retryRendererChunk()
  fallbackActive.value = false
  mountKey.value += 1
}

function useFallback(): void {
  if (disposed) return
  failure.value = null
  fallbackActive.value = true
}

function forward(interaction: AllocationInteraction): void {
  if (!disposed) emit('update:interaction', interaction)
}
</script>

<style scoped>
.allocation-chart {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.allocation-chart__reason {
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  padding: 12px;
  color: #172b4d;
  background: #f7f8fa;
  margin: 8px 0;
}

.allocation-chart__failure {
  border: 1px solid #b3261e;
  border-radius: 8px;
  padding: 12px;
  color: #b3261e;
  background: #fff;
  display: grid;
  gap: 8px;
  justify-items: start;
}

.allocation-chart__failure-actions {
  display: flex;
  gap: 8px;
}

.allocation-chart__failure button {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>
