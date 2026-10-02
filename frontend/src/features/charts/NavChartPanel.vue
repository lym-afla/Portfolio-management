<template>
  <!-- Panel composition (C3): wraps the incumbent NAVChart and supplies its
       named chart slot ONLY when policy selects the ECharts pilot. Query
       controls stay single-owned by NAVChart; no duplicated controls, no
       renderer-driven data requests. The incumbent renderer receives a fresh
       detached legacy copy, keeping the retained validated result immune to
       renderer mutation. -->
  <div class="nav-chart-panel">
    <v-alert
      v-if="error"
      type="error"
      class="mb-2"
      data-testid="nav-error"
    >
      {{ error }}
      <v-btn
        color="error"
        variant="outlined"
        class="ml-2"
        data-testid="nav-retry"
        @click="emit('retry')"
      >
        Retry
      </v-btn>
    </v-alert>
    <v-alert
      v-else-if="legacyOnlyNotice"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-2"
      data-testid="nav-capability-notice"
    >
      {{ legacyOnlyNotice }}
    </v-alert>
    <v-alert
      v-if="fallbackNotice"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-2"
      data-testid="nav-fallback-notice"
    >
      {{ fallbackNotice }}
    </v-alert>
    <v-skeleton-loader v-if="loading && !result" type="card" height="400" />
    <NAVChart
      v-else-if="result"
      data-testid="nav-chart"
      :chart-data="legacyCopy"
      :loading="updating"
      :initial-params="initialParams"
      :effective-current-date="effectiveCurrentDate"
      @update-params="forwardParams"
    >
      <template v-if="pilotSlotActive" #chart>
        <div class="nav-chart-panel__pilot" data-testid="nav-echarts-pilot">
          <v-alert
            v-if="emptyDocument"
            type="info"
            variant="tonal"
            density="compact"
            text="No data for the selected account and period. Adjust the date range or select another account."
          />
          <template v-else>
            <ChartHost
              :result="result"
              :interaction="interaction"
              :requested="requestedRenderer"
              :loading="loading"
              @update:interaction="interaction = $event"
              @fallback="useFallback"
            />
            <ChartLegend
              :document="v2Document"
              :interaction="interaction"
              @update:interaction="interaction = $event"
            />
            <ChartInspection
              :document="v2Document"
              :interaction="interaction"
              @update:interaction="interaction = $event"
            />
            <ChartDataTable
              :document="v2Document"
              :interaction="interaction"
              @update:interaction="interaction = $event"
            />
          </template>
        </div>
      </template>
    </NAVChart>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRaw, watch } from 'vue'
import NAVChart from '@/components/dashboard/NAVChart.vue'
import type { NavResult } from './contracts'
import type { ChartInteraction } from './interaction'
import { defaultInteraction, reconcileInteraction } from './interaction'
import { pilotRequested, resolveRenderer } from './rendererPolicy'
import ChartHost from './ChartHost.vue'
import ChartLegend from './ChartLegend.vue'
import ChartDataTable from './ChartDataTable.vue'
import ChartInspection from './ChartInspection.vue'

const props = defineProps<{
  result: NavResult | null
  loading: boolean
  updating?: boolean
  error?: string
  initialParams: object
  effectiveCurrentDate: string
}>()

const emit = defineEmits<{
  (e: 'update-params', params: object): void
  (e: 'retry'): void
}>()

const requestedRenderer = computed(() => (pilotRequested() ? 'echarts' : 'chartjs') as 'echarts' | 'chartjs')
const useLegacyFallback = ref(false)

const pilotSlotActive = computed(() => {
  if (useLegacyFallback.value) return false
  if (!props.result) return false
  return resolveRenderer(requestedRenderer.value, props.result) === 'echarts'
})

const legacyOnlyNotice = computed(() => {
  if (props.error || !props.result) return null
  return props.result.capability === 'legacy_only'
    ? 'Chart data comes from a legacy response without the exact chart contract; values are unverified metadata.'
    : null
})

const fallbackNotice = computed(() =>
  useLegacyFallback.value
    ? 'The pilot chart could not be drawn; the previous chart is shown with the same accepted data.'
    : null,
)

const emptyDocument = computed(() => v2Document.value?.outcome === 'empty')

// Templates cannot narrow the capability discriminant; narrow it here.
const v2Document = computed(() => (props.result?.capability === 'v2' ? props.result.document : null))

// The incumbent renderer owns a fresh detached copy per result; the retained
// validated result survives Chart.js-side mutation untouched. toRaw avoids
// cloning Vue's prop proxies.
const legacyCopy = computed(() => {
  if (!props.result) return null
  const raw = toRaw(props.result)
  return structuredClone(raw.legacy)
})

const interaction = ref<ChartInteraction>({ visibleSeriesIds: [], viewport: null, inspectedPeriodKey: null })

// Reconcile interaction across same-context refreshes; a context
// invalidation (result cleared) resets state before new labels apply.
watch(
  () => props.result,
  (next, previous) => {
    if (!next) {
      interaction.value = { visibleSeriesIds: [], viewport: null, inspectedPeriodKey: null }
      return
    }
    if (next.capability !== 'v2') return
    interaction.value = previous && previous.capability === 'v2'
      ? reconcileInteraction(previous.document, next.document, interaction.value)
      : defaultInteraction(next.document)
  },
)

function useFallback(): void {
  useLegacyFallback.value = true
}

function forwardParams(params: object): void {
  emit('update-params', params)
}
</script>

<style scoped>
.nav-chart-panel__pilot {
  display: grid;
  gap: 12px;
  min-width: 0;
}
</style>
