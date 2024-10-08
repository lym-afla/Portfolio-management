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
    @update-error="handleUpdateError"
  />
  <ProgressDialog
    v-model="showProgressDialog"
    :title="'Updating Broker Performance'"
    :progress="updateProgress"
    :current="currentOperation"
    :total="totalOperations"
    :currentMessage="currentMessage"
    :errors="errors"
    @stop-import="handleStopImport"
  />
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import UpdateBrokerPerformanceDialog from '@/components/dialogs/UpdateBrokerPerformanceDialog.vue'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'
import { updateBrokerPerformance } from '@/services/api'

export default {
  name: 'SummaryOverTimeTable',
  components: {
    UpdateBrokerPerformanceDialog,
    ProgressDialog
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
    const showProgressDialog = ref(false)
    const updateProgress = ref(0)
    const currentOperation = ref(0)
    const totalOperations = ref(0)
    const currentMessage = ref('')
    const errors = ref([])

    const showUpdateDialog = () => {
      showDialog.value = true
    }

    const handleUpdateStarted = async (formData) => {
      console.log('Update started', formData)
      showProgressDialog.value = true
      currentMessage.value = 'Starting update'
      updateProgress.value = 0
      currentOperation.value = 0
      totalOperations.value = 0
      errors.value = []

      try {
        await updateBrokerPerformance(formData)
      } catch (error) {
        handleUpdateError(error.message)
      }
    }

    const handleProgress = (event) => {
      const data = event.detail
      console.log('Progress:', data)
      if (data.status === 'initializing') {
        totalOperations.value = data.total
      } else if (data.status === 'progress') {
        updateProgress.value = data.progress
        currentOperation.value = data.current
        // totalOperations.value = data.total
        currentMessage.value = compileProgressMessage(data)
      } else if (data.status === 'complete') {
        // showProgressDialog.value = false
        emit('refresh-data')
      } else if (data.status === 'error') {
        errors.value.push(data.message)
        console.error('Update error:', data.message)
      }
    }

    const compileProgressMessage = (data) => {
      return `Processing year ${data.year}, currency: ${data.currency}, restricted: ${data.is_restricted}`
    }

    const handleUpdateError = (error) => {
      console.error('Update error:', error)
      errors.value.push(error)
      currentMessage.value = `Error: ${error}`
    }

    const handleStopImport = () => {
      // Implement stop import logic here
      console.log('Stop import requested')
      showProgressDialog.value = false
    }

    onMounted(() => {
      window.addEventListener('brokerPerformanceUpdateProgress', handleProgress)
    })

    onUnmounted(() => {
      window.removeEventListener('brokerPerformanceUpdateProgress', handleProgress)
    })

    return {
      showDialog,
      showProgressDialog,
      showUpdateDialog,
      handleUpdateStarted,
      handleUpdateError,
      updateProgress,
      currentOperation,
      totalOperations,
      currentMessage,
      errors,
      handleStopImport
    }
  }
}
</script>

<style scoped>
.highlight {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>