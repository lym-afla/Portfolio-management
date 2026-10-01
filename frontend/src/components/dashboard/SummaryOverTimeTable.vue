<template>
  <div class="summary-over-time">
    <v-alert v-if="error" type="error" dismissible>
      {{ error }}
    </v-alert>
    <div v-else class="workspace-table-region">
      <v-table v-if="lines && years && currentYear" density="compact">
        <thead>
          <tr>
            <th />
            <th
              v-for="year in years"
              :key="year"
              class="text-center font-weight-bold"
            >
              {{ year }}
            </th>
            <th class="text-center highlight font-weight-bold">
              {{ currentYear }}YTD
            </th>
            <th class="text-center highlight font-weight-bold">All-time</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="line in lines"
            :key="line.name"
            :class="{
              'font-weight-bold':
                line.name === 'BoP NAV' || line.name === 'EoP NAV',
              'font-italic': line.name === 'TSR',
            }"
          >
            <td>
              {{ line.name }}
            </td>
            <td
              v-for="year in years"
              :key="`${line.name}-${year}`"
              class="text-center"
            >
              {{ line.data[year] }}
            </td>
            <td class="text-center highlight">{{ line.data['YTD'] }}</td>
            <td class="text-center font-weight-bold highlight">
              {{ line.data['All-time'] }}
            </td>
          </tr>
        </tbody>
      </v-table>
      <v-alert v-else type="info" variant="tonal" density="compact"
        text="No data for the selected account and period. Adjust the date range or select another account." />
    </div>
  </div>

  <UpdateAccountPerformanceDialog v-if="showDialogMounted"
    v-model="showDialog"
    @update-started="handleUpdateStarted"
    @update-error="handleUpdateError"
  />
  <ProgressDialog v-if="showProgressDialogMounted"
    v-model="showProgressDialog"
    :title="'Updating Account Performance'"
    :progress="updateProgress"
    :current="currentOperation"
    :total="totalOperations"
    :currentMessage="currentMessage"
    :errors="errors"
    @stop-import="handleStopImport"
  />
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, onMounted, onUnmounted } from 'vue'
const UpdateAccountPerformanceDialog = defineAppDialog(() => import('@/components/dialogs/UpdateAccountPerformanceDialog.vue'))
const ProgressDialog = defineAppDialog(() => import('@/components/dialogs/ProgressDialog.vue'))
import { updateAccountPerformance } from '@/services/api'
import logger from '@/utils/logger'

defineProps({
  lines: {
    type: Array,
    default: () => [],
  },
  years: {
    type: Array,
    default: () => [],
  },
  currentYear: {
    type: String,
    default: '',
  },
  error: {
    type: String,
    default: '',
  },
})
const emit = defineEmits(['refresh-data'])

const showDialog = ref(false)
const showDialogMounted = useFirstOpen(showDialog)
const showProgressDialog = ref(false)
const showProgressDialogMounted = useFirstOpen(showProgressDialog)
const updateProgress = ref(0)
const currentOperation = ref(0)
const totalOperations = ref(0)
const currentMessage = ref('')
const errors = ref([])

function showUpdateDialog() {
  showDialog.value = true
}

// The Update Account Performance action lives in the surrounding history
// section header; this exposes the dialog opener to that parent.
defineExpose({ openUpdateDialog: showUpdateDialog })

async function handleUpdateStarted(formData) {
  showDialog.value = false
  showProgressDialog.value = true
  currentMessage.value = 'Starting update'
  updateProgress.value = 0
  currentOperation.value = 0
  totalOperations.value = 0
  errors.value = []

  try {
    await updateAccountPerformance(formData)
    emit('refresh-data')
  } catch (error) {
    handleUpdateError(error)
  }
}

function handleProgress(event) {
  const data = event.detail
  logger.log('Unknown', 'Progress:', data)

  if (!showProgressDialog.value) {
    showProgressDialog.value = true
  }

  switch (data.status) {
    case 'initializing':
      totalOperations.value = data.total
      break

    case 'progress':
      updateProgress.value = data.progress
      currentOperation.value = data.current
      currentMessage.value = compileProgressMessage(data)
      break

    case 'complete':
      emit('refresh-data')
      setTimeout(() => {
        showProgressDialog.value = false
      }, 1000)
      break

    case 'error':
      handleUpdateError(data.message)
      break
  }
}

function compileProgressMessage(data) {
  return `Processing year ${data.year}, currency: ${data.currency}, restricted: ${data.is_restricted}`
}

function handleUpdateError(error) {
  logger.error('Unknown', '[handleUpdateError] Update error:', error)
  const errorMessage =
    error.response?.data?.message || error.message || String(error)
  errors.value.push(errorMessage)
  currentMessage.value = `Error: ${errorMessage}`
}

function handleStopImport() {
  // Implement stop import logic here
  logger.log('Unknown', 'Stop import requested')
  showProgressDialog.value = false
}

onMounted(() => {
  window.addEventListener(
    'accountPerformanceUpdateProgress',
    handleProgress
  )
  window.addEventListener(
    'accountPerformanceUpdateError',
    handleUpdateError
  )
})

onUnmounted(() => {
  window.removeEventListener(
    'accountPerformanceUpdateProgress',
    handleProgress
  )
  window.removeEventListener(
    'accountPerformanceUpdateError',
    handleUpdateError
  )
})
</script>

<style scoped>
.highlight {
  background-color: rgba(var(--v-theme-primary), 0.08);
}
</style>
