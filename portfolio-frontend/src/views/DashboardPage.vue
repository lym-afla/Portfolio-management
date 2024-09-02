<template>
  <div class="dashboard-page">
    <h1>Dashboard</h1>
    <DashboardSummary />
    Test text
    <v-container>
        <v-row justify="center">
          <v-date-picker
          show-adjacent-months
          elevation="24"
          
          ></v-date-picker>
        </v-row>
      </v-container>
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