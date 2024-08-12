<template>
  <div class="nav-chart">
    <h3>NAV Chart</h3>
    <!-- We'll add the chart library (e.g., Chart.js) implementation here -->
  </div>
</template>

<script>
import axios from 'axios'
import { API_BASE_URL } from '@/config'

export default {
  name: 'NAVChart',
  data() {
    return {
      chartData: null,
    }
  },
  mounted() {
    this.fetchChartData()
  },
  methods: {
    fetchChartData() {
      const params = {
        frequency: 'monthly', // You might want to make this configurable
        from: '2023-01-01', // These should be dynamic
        to: '2023-12-31',
        breakdown: 'asset_type',
      }
      axios
        .get(`${API_BASE_URL}/dashboard/get_nav_chart_data`, { params })
        .then((response) => {
          this.chartData = response.data
          // Here you would initialize or update your chart
          console.log('Chart data received:', this.chartData)
        })
        .catch((error) => {
          console.error('Error fetching NAV chart data:', error)
        })
    },
  },
}
</script>
