<template>
  <v-container fluid class="pa-0">
    <v-row class="equal-height-row">
      <v-col cols="12" md="3">
        <v-skeleton-loader v-if="loading.summary" type="card" class="h-100" />
        <SummaryCard v-else :summary="summary" :currency="currency" class="h-100" />
      </v-col>
      <v-col cols="12" md="9">
        <v-row class="equal-height-row h-100">
          <v-col cols="12" md="4">
            <v-skeleton-loader v-if="loading.breakdownCharts" type="card" class="h-100" />
            <BreakdownChart v-else title="Asset Type" :data="breakdownData.assetType" class="h-100" />
          </v-col>
          <v-col cols="12" md="4">
            <v-skeleton-loader v-if="loading.breakdownCharts" type="card" class="h-100" />
            <BreakdownChart v-else title="Asset Class" :data="breakdownData.assetClass" class="h-100" />
          </v-col>
          <v-col cols="12" md="4">
            <v-skeleton-loader v-if="loading.breakdownCharts" type="card" class="h-100" />
            <BreakdownChart v-else title="Currency" :data="breakdownData.currency" class="h-100" />
          </v-col>
        </v-row>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-skeleton-loader v-if="loading.summaryOverTime" type="table" />
        <SummaryOverTimeTable
          :lines="summaryOverTimeData.lines"
          :years="summaryOverTimeData.years"
          :currentYear="summaryOverTimeData.currentYear"
        />
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-skeleton-loader v-if="loading.navChart" type="card" />
        <NAVChart 
          v-else
          :initialData="navChartData" 
        />
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import SummaryCard from '@/components/dashboard/SummaryCard.vue'
import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'
import SummaryOverTimeTable from '@/components/dashboard/SummaryOverTimeTable.vue'
import NAVChart from '@/components/dashboard/NAVChart.vue'
import { getSummaryData, getBreakdownData } from '@/services/api'
import { mockDashboardData } from '@/mockData'

export default {
  name: 'DashboardPage',
  components: {
    SummaryCard,
    BreakdownChart,
    SummaryOverTimeTable,
    NAVChart,
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const summary = ref({})
    const currency = ref('USD')
    const breakdownData = ref({
      assetType: {},
      assetClass: {},
      currency: {},
    })
    const summaryOverTimeData = ref(mockDashboardData.summaryOverTimeData)
    const navChartData = ref(mockDashboardData.navChartData)

    const loading = ref({
      summary: true,
      breakdownCharts: true,
    })

    const fetchSummaryData = async () => {
      try {
        const data = await getSummaryData()
        summary.value = data
        loading.value.summary = false
      } catch (error) {
        console.error('Error fetching summary data:', error)
      }
    }

    const fetchBreakdownData = async () => {
      try {
        const data = await getBreakdownData()
        breakdownData.value = data
        loading.value.breakdownCharts = false
      } catch (error) {
        console.error('Error fetching breakdown data:', error)
      }
    }

    onMounted(() => {
      emit('update-page-title', 'Dashboard')
      fetchSummaryData()
      fetchBreakdownData()
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      summary,
      currency,
      breakdownData,
      summaryOverTimeData,
      navChartData,
      loading,
    }
  },
}
</script>

<style scoped>
.equal-height-row {
  display: flex;
  flex-wrap: wrap;
}

.equal-height-row > [class*='col-'] {
  display: flex;
  flex-direction: column;
}

.equal-height-row .v-card {
  flex: 1 1 auto;
}

.h-100 {
  height: 100%;
}
</style>