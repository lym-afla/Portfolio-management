<template>
  <div class="dashboard-page">
    <h1>Dashboard</h1>
    <DashboardSummary />
    <!-- <NAVChart /> -->
  </div>
</template>

<script>
import DashboardSummary from '@/components/DashboardSummary.vue'
// import NAVChart from '@/components/NAVChart.vue'

export default {
  name: 'DashboardPage',
  components: {
    DashboardSummary,
    // NAVChart
  }
}
</script>