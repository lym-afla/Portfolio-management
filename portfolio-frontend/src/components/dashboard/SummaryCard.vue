<template>
  <v-card class="summary-card">
    <v-card-title class="text-h5 font-weight-bold">
      <v-icon left color="primary" class="mr-2">mdi-chart-box</v-icon>
      Portfolio Summary
    </v-card-title>
    <v-card-text class="pa-0">
      <v-table density="compact">
        <thead>
          <tr>
            <th class="text-left">Metric</th>
            <th class="text-right">{{ props.currency }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(value, key) in props.summary" :key="key">
            <td class="text-left">{{ formatKey(key) }}</td>
            <td class="text-right">{{ formatValue(value) }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  name: 'SummaryCard',
  props: {
    summary: {
      type: Object,
      required: true
    },
    currency: {
      type: String,
      default: 'USD'
    }
  },
  setup(props) {
    const formatKey = (key) => {
      return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }

    const formatValue = (value) => {
      if (typeof value === 'number') {
        return new Intl.NumberFormat('en-US', {
          style: 'decimal',
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        }).format(value)
      } else if (typeof value === 'string' && value.endsWith('%')) {
        return value
      } else {
        return value
      }
    }

    return {
      formatKey,
      formatValue,
      props // Return props to make them accessible in the template
    }
  }
}
</script>

<style scoped>
.summary-card {
  background-color: #f8f9fa !important;
  border-left: 4px solid var(--v-primary-base) !important;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
  padding-bottom: 10px;
}

.summary-card .v-card-title {
  color: var(--v-primary-base);
  font-size: 1.5rem !important;
  padding-top: 16px;
  padding-bottom: 16px;
}

.summary-card .v-table {
  background-color: transparent !important;
}

.summary-card .v-table th {
  font-weight: bold !important;
  font-size: 1.1rem;
}

.summary-card .v-table td {
  font-size: 1.05rem;
}
</style>