<template>
  <v-card v-if="lines && years && currentYear">
    <v-card-title>Summary Over Time</v-card-title>
    <v-card-text>
      <v-alert v-if="error" type="error" dismissible>
        {{ error }}
      </v-alert>
      <v-table v-if="!error" density="compact">
        <thead>
          <tr>
            <th></th>
            <th v-for="year in years" :key="year" class="text-center font-weight-bold">{{ year }}</th>
            <th class="text-center highlight font-weight-bold">{{ currentYear }}YTD</th>
            <th class="text-center highlight font-weight-bold">All-time</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in lines" :key="line.name" :class="{ 'font-weight-bold': line.name === 'BoP NAV' || line.name === 'EoP NAV', 'font-italic': line.name === 'TSR' }">
            <td>
              {{ line.name }}
            </td>
            <td v-for="year in years" :key="`${line.name}-${year}`" class="text-center">
              {{ line.data[year] }}
            </td>
            <td class="text-center highlight">{{ line.data['YTD'] }}</td>
            <td class="text-center font-weight-bold highlight">{{ line.data['All-time'] }}</td>
          </tr>
        </tbody>
      </v-table>
      <v-btn @click="showUpdateDialog" color="primary" class="mt-4">Update Broker Performance</v-btn>
    </v-card-text>
  </v-card>
  <v-card v-else>
    <v-card-title>Summary Over Time</v-card-title>
    <v-card-text>
      <v-alert type="info">
        No data available for the selected broker.
      </v-alert>
      <v-btn @click="showUpdateDialog" color="primary" class="mt-4">Update Broker Performance</v-btn>
    </v-card-text>
  </v-card>

  <UpdateBrokerPerformanceDialog
    v-model="showDialog"
    @update-started="handleUpdateStarted"
    @update-progress="handleUpdateProgress"
    @update-completed="handleUpdateCompleted"
    @update-error="handleUpdateError"
  />
</template>

<script>
import { ref } from 'vue'
import UpdateBrokerPerformanceDialog from '@/components/dialogs/UpdateBrokerPerformanceDialog.vue'

export default {
  name: 'SummaryOverTimeTable',
  components: {
    UpdateBrokerPerformanceDialog
  },
  props: {
    lines: {
      type: Array,
      default: () => []
    },
    years: {
      type: Array,
      default: () => []
    },
    currentYear: {
      type: String,
      default: ''
    },
    error: {
      type: String,
      default: ''
    }
  },
  emits: ['refresh-data'],
  setup(props, { emit }) {
    const showDialog = ref(false)

    const showUpdateDialog = () => {
      showDialog.value = true
    }

    const handleUpdateStarted = () => {
      console.log('Update started')
    }

    const handleUpdateProgress = (data) => {
      console.log('Update progress:', data)
    }

    const handleUpdateCompleted = () => {
      console.log('Update completed')
      emit('refresh-data')
    }

    const handleUpdateError = (error) => {
      console.error('Update error:', error)
    }

    return {
      showDialog,
      showUpdateDialog,
      handleUpdateStarted,
      handleUpdateProgress,
      handleUpdateCompleted,
      handleUpdateError
    }
  }
}
</script>

<style scoped>
.highlight {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>
