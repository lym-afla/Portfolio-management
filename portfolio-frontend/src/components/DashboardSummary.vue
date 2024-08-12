<template>
  <div class="dashboard-summary">
    <h2>Dashboard Summary</h2>
    <p>Total Value: {{ totalValue }}</p>
    <p>Change: {{ change }}</p>
  </div>
</template>

<script>
// import axios from 'axios'
// import { API_BASE_URL } from '@/config'

export default {
  name: 'DashboardSummary',
  data() {
    return {
      totalValue: 0,
      change: '0%'
    }
  },
  mounted() {
    this.fetchSummaryData()
  },
  methods: {
    fetchSummaryData() {
      // axios.get(`${API_BASE_URL}/api/dashboard-summary/`)
      //   .then(response => {
      //     this.totalValue = response.data.totalValue
      //     this.change = response.data.change
      //   })
      //   .catch(error => {
      //     console.error('Error fetching dashboard summary:', error)
      //   })
    }
  }
}
</script>