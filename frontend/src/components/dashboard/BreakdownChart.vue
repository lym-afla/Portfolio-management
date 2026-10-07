<template>
  <v-card class="d-flex flex-column">
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text class="pa-0 flex-grow-1 d-flex flex-column">
      <v-tabs v-model="tab" v-if="hasData">
        <v-tab value="chart">Chart</v-tab>
        <v-tab value="table">Table</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="flex-grow-1" v-if="hasData">
        <v-window-item value="chart">
          <!-- C4: when the dashboard hands over a validated allocation
               document, the chart tab is the gated modern composition (solid
               pie, or the certified reason when ineligible); the fallback
               slot keeps the incumbent bars one click away. C5a: the legacy
               leaf (and its Chart.js runtime) loads only when it renders.
               Review round: the download-failure alert renders ABOVE the
               branches — replacing them would unmount AllocationChart and
               destroy the user's fallback choice, so a retry would remount
               the modern chart instead of the chosen legacy one. -->
          <div v-if="legacyLoadError" class="chart-leaf-error" data-testid="allocation-legacy-load-error" role="alert">
            <p>The chart could not be loaded: {{ legacyLoadError.message }}</p>
            <button type="button" data-testid="allocation-legacy-load-retry" @click="retryLegacyLoad">Retry chart</button>
          </div>
          <AllocationChart
            v-if="chartDocument"
            :document="chartDocument"
            :interaction="allocationInteraction"
            :requested="true"
            @update:interaction="allocationInteraction = $event"
          >
            <template #fallback>
              <LegacyAllocationChart :data="chartData" :options="barChartOptions" />
            </template>
          </AllocationChart>
          <LegacyAllocationChart v-else :data="chartData" :options="barChartOptions" />
        </v-window-item>

        <v-window-item value="table">
          <AllocationDataTable
            v-if="chartDocument"
            :document="chartDocument"
            :interaction="allocationInteraction"
            @update:interaction="allocationInteraction = $event"
          />
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th class="text-left category-column" />
                <th class="text-right font-weight-bold">{{ currency }}</th>
                <th class="text-right font-weight-bold font-italic">%</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in sortedData" :key="index">
                <td class="text-left category-column">{{ item.label }}</td>
                <td class="text-right">{{ item.value }}</td>
                <td class="text-right font-italic">{{ item.percentage }}</td>
              </tr>
              <tr class="font-weight-bold">
                <td class="text-left category-column">Total</td>
                <td class="text-right">{{ props.totalNAV }}</td>
                <td class="text-right font-italic">100%</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
      </v-window>

      <v-alert v-if="!hasData" type="info" variant="tonal" density="compact"
        text="No data for the selected account and period. Adjust the date range or select another account." />
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { getChartOptions, colorPalette } from '@/config/chartConfig'
import AllocationChart from '@/features/charts/AllocationChart.vue'
import AllocationDataTable from '@/features/charts/AllocationDataTable.vue'
import { lazyChartRenderer } from '@/features/charts/lazyRenderer'
import {
  defaultAllocationInteraction,
  reconcileAllocationInteraction,
} from '@/features/charts/allocationInteraction'

// C5a: the incumbent Chart.js leaf is the only remaining Chart.js import for
// the allocation cards, and it loads through an async boundary so a modern
// route never downloads the legacy runtime. A rejected chunk download shows
// a visible, recoverable error instead of an empty card.
const {
  component: LegacyAllocationChart,
  loadError: legacyLoadError,
  retry: retryLegacyLoad,
} = lazyChartRenderer(() => import('@/components/charts/LegacyAllocationChart.vue'))

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  data: {
    type: Object,
    default: () => ({}),
  },
  totalNAV: {
    type: String,
  },
  currency: {
    type: String,
    required: true,
  },
  // C4: the card's validated allocation document, handed over only while the
  // allocation gate is on and the negotiated result is v2. Null keeps the
  // incumbent presentation byte-identical.
  chartDocument: {
    type: Object,
    default: null,
  },
})

const tab = ref('chart')
const barChartOptions = ref({})
// Highlight-only interaction (C4): focus never hides or renormalizes; a
// compatible refresh keeps the focus, a disappearing category clears it.
const allocationInteraction = ref(defaultAllocationInteraction())
watch(
  () => props.chartDocument,
  (next, previous) => {
    if (!next) {
      allocationInteraction.value = defaultAllocationInteraction()
      return
    }
    allocationInteraction.value = reconcileAllocationInteraction(
      previous ?? next,
      next,
      allocationInteraction.value,
    )
  },
  { immediate: true },
)

const hasData = computed(() => {
  return (
    props.data && props.data.data && Object.keys(props.data.data).length > 0
  )
})

// Sort descending, then reverse so the biggest bar renders at the top
// (Chart.js y-axis places the first label at the top).
const sortedData = computed(() => {
  if (!hasData.value) return []
  return Object.entries(props.data.data)
    .map(([label, value]) => ({
      label,
      value,
      percentage: props.data.percentage[label],
    }))
    .filter(
      (item) =>
        item.value !== '–' &&
        parseFloat(item.value.replace(/[^0-9.-]+/g, '')) !== 0
    )
    .sort(
      (a, b) =>
        parseFloat(b.value.replace(/[^0-9.-]+/g, '')) -
        parseFloat(a.value.replace(/[^0-9.-]+/g, ''))
    )
    .reverse()
})

const chartData = computed(() => {
  if (!hasData.value) return { labels: [], datasets: [] }

  return {
    labels: sortedData.value.map((item) => item.label),
    datasets: [
      {
        data: sortedData.value.map((item) =>
          parseFloat(item.value.replace(/[^0-9.-]+/g, ''))
        ),
        backgroundColor: colorPalette.slice(0, sortedData.value.length),
      },
    ],
  }
})

onMounted(async () => {
  const { barChartOptions: options } = await getChartOptions()
  barChartOptions.value = options
})
</script>
<style scoped>
.v-window-item {
  height: 100%;
  width: 100%;
}

.chart-leaf-error {
  border: 1px solid #b3261e;
  border-radius: 8px;
  padding: 12px;
  color: #b3261e;
  background: #fff;
  display: grid;
  gap: 8px;
  justify-items: start;
}

.chart-leaf-error button {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
}

.v-table :deep(th) {
  font-weight: bold;
}

.v-table :deep(td),
.v-table :deep(th) {
  padding: 0 16px !important;
}
</style>
