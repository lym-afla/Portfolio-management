<template>
  <!-- Renderer boundary (C3): hosts the lazy ECharts pilot only when policy
       selects it; the incumbent renderer stays the default slot. Render
       failures are recoverable with an explicit retry and an explicit
       user-chosen fallback backed by the same accepted result — transport or
       contract errors remain the Dashboard/C2 error state and never reach
       this host as empty charts. -->
  <div class="chart-host" :aria-busy="loading ? 'true' : undefined">
    <EChartsNav
      v-if="renderer === 'echarts' && v2Document && !failure"
      :key="mountKey"
      :document="v2Document"
      :interaction="interaction"
      @update:interaction="forward"
      @render-error="onRenderError"
    />
    <slot v-else />
    <div v-if="failure" class="chart-host__failure" data-testid="chart-render-error" role="alert">
      <p>The pilot chart could not be drawn: {{ failure.message }}</p>
      <div class="chart-host__failure-actions">
        <button type="button" data-testid="chart-render-retry" @click="retry">Retry chart</button>
        <button type="button" data-testid="chart-render-fallback" @click="usePrevious">Use previous chart</button>
      </div>
    </div>
    <div v-if="loading && !failure" class="chart-host__overlay" aria-hidden="true">
      <span class="chart-host__spinner" role="presentation" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onErrorCaptured, onUnmounted, ref } from 'vue'
import type { NavResult } from './contracts'
import type { ChartInteraction } from './interaction'
import { resolveRenderer, type Renderer } from './rendererPolicy'

const EChartsNav = defineAsyncComponent(() => import('./EChartsNav.vue'))

const props = withDefaults(
  defineProps<{
    result: NavResult
    interaction: ChartInteraction
    requested?: Renderer
    loading?: boolean
  }>(),
  { requested: 'chartjs', loading: false },
)

const emit = defineEmits<{
  (e: 'fallback'): void
  (e: 'update:interaction', interaction: ChartInteraction): void
}>()

const failure = ref<Error | null>(null)
const mountKey = ref(0)
let disposed = false

const renderer = computed<Renderer>(() => resolveRenderer(props.requested, props.result))

// Templates cannot narrow the capability discriminant; narrow it here.
const v2Document = computed(() => (props.result.capability === 'v2' ? props.result.document : null))

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
  mountKey.value += 1
}

function usePrevious(): void {
  if (disposed) return
  failure.value = null
  emit('fallback')
}

function forward(interaction: ChartInteraction): void {
  if (!disposed) emit('update:interaction', interaction)
}

onUnmounted(() => {
  disposed = true
})
</script>

<style scoped>
.chart-host {
  position: relative;
  min-height: 360px;
}

.chart-host__overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-host__spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #e2e6eb;
  border-top-color: #0f4c81;
  border-radius: 50%;
  animation: chart-host-spin 0.8s linear infinite;
}

@keyframes chart-host-spin {
  to {
    transform: rotate(360deg);
  }
}

.chart-host__failure {
  border: 1px solid #b3261e;
  border-radius: 8px;
  padding: 12px;
  color: #b3261e;
  background: #fff;
  display: grid;
  gap: 8px;
  justify-items: start;
}

.chart-host__failure-actions {
  display: flex;
  gap: 8px;
}

.chart-host__failure button {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>
