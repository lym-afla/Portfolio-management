<template>
  <!-- Modern security history composition (C4): the view-only zoomable line
       plus the exact observed-point table. Empty documents show a no-data
       notice instead of an empty canvas. Rendering failures are recoverable
       with an explicit retry or the explicit user-chosen legacy fallback
       (the incumbent Chart.js chart, supplied through the fallback slot)
       backed by the same accepted result — data errors never reach this
       component. -->
  <div class="security-history-chart" data-testid="security-history-chart">
    <template v-if="requested && !fallbackActive">
      <div
        v-if="emptyDocument"
        class="security-history-chart__empty"
        data-testid="security-history-empty"
        role="status"
      >
        No {{ document.kind === 'position' ? 'position' : 'price' }} history for the selected period.
        Adjust the time range or record transactions.
      </div>
      <template v-else>
        <div class="security-history-chart__canvas">
          <EChartsSecurity
            v-if="!failure"
            :key="mountKey"
            :document="document"
            :interaction="interaction"
            @update:interaction="forward"
            @render-error="onRenderError"
          />
        </div>
        <div v-if="failure" class="security-history-chart__failure" data-testid="security-render-error" role="alert">
          <p>The chart could not be drawn: {{ failure.message }}</p>
          <div class="security-history-chart__failure-actions">
            <button type="button" data-testid="security-render-retry" @click="retry">Retry chart</button>
            <button type="button" data-testid="security-render-fallback" @click="useFallback">Use previous chart</button>
          </div>
        </div>
        <SecurityDataTable
          v-if="!failure"
          :document="document"
        />
      </template>
    </template>
    <slot v-else name="fallback" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onErrorCaptured, onUnmounted, ref } from 'vue'
import type { ChartDocument } from './contracts'
import type { SecurityInteraction } from './securityInteraction'
import { defaultSecurityInteraction } from './securityInteraction'
import SecurityDataTable from './SecurityDataTable.vue'

const EChartsSecurity = defineAsyncComponent(() => import('./EChartsSecurity.vue'))

const props = withDefaults(
  defineProps<{
    document: ChartDocument
    interaction?: SecurityInteraction
    requested: boolean
  }>(),
  { interaction: () => defaultSecurityInteraction() },
)

const emit = defineEmits<{
  (e: 'update:interaction', interaction: SecurityInteraction): void
}>()

const failure = ref<Error | null>(null)
const fallbackActive = ref(false)
const mountKey = ref(0)
let disposed = false

onUnmounted(() => {
  disposed = true
})

const emptyDocument = computed(() => props.document.outcome === 'empty')

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
  fallbackActive.value = false
  mountKey.value += 1
}

function useFallback(): void {
  if (disposed) return
  failure.value = null
  fallbackActive.value = true
}

function forward(interaction: SecurityInteraction): void {
  if (!disposed) emit('update:interaction', interaction)
}
</script>

<style scoped>
.security-history-chart {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.security-history-chart__canvas {
  height: 320px;
  min-width: 0;
}

.security-history-chart__empty {
  min-width: 0;
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  padding: 12px;
  color: #172b4d;
  background: #f7f8fa;
}

.security-history-chart__failure {
  border: 1px solid #b3261e;
  border-radius: 8px;
  padding: 12px;
  color: #b3261e;
  background: #fff;
  display: grid;
  gap: 8px;
  justify-items: start;
}

.security-history-chart__failure-actions {
  display: flex;
  gap: 8px;
}

.security-history-chart__failure button {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>
