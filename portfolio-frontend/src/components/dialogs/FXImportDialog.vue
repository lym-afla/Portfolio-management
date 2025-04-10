<template>
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h5 pb-2"> Import FX Rates </v-card-title>
      <v-card-text>
        <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>

        <v-select
          v-model="importType"
          :items="importTypes"
          item-title="text"
          item-value="value"
          label="Import Type"
          :disabled="isImporting"
        />

        <v-row v-if="importType === 'auto' && stats" class="mb-4">
          <v-col cols="12" sm="4">
            <v-card elevation="2" class="pa-2 text-center">
              <v-icon color="primary" size="large" class="mb-2"
                >mdi-calendar-range</v-icon
              >
              <v-card-title class="text-h6">{{
                stats.total_dates
              }}</v-card-title>
              <v-card-subtitle>Total Dates</v-card-subtitle>
            </v-card>
          </v-col>
          <v-col cols="12" sm="4">
            <v-card elevation="2" class="pa-2 text-center">
              <v-icon color="error" size="large" class="mb-2"
                >mdi-currency-usd-off</v-icon
              >
              <v-card-title class="text-h6">{{
                stats.missing_instances
              }}</v-card-title>
              <v-card-subtitle>Missing FX</v-card-subtitle>
            </v-card>
          </v-col>
          <v-col cols="12" sm="4">
            <v-card elevation="2" class="pa-2 text-center">
              <v-icon color="warning" size="large" class="mb-2"
                >mdi-currency-usd</v-icon
              >
              <v-card-title class="text-h6">{{
                stats.incomplete_instances
              }}</v-card-title>
              <v-card-subtitle>Incomplete FX</v-card-subtitle>
            </v-card>
          </v-col>
        </v-row>

        <template v-if="importType === 'auto'">
          <v-select
            v-model="importOption"
            :items="importOptions"
            item-title="text"
            item-value="value"
            label="Import Option"
            :disabled="isImporting"
          />
        </template>

        <template v-else-if="importType === 'manual'">
          <v-radio-group v-model="dateType" row>
            <v-radio label="Single Date" value="single" />
            <v-radio label="Date Range" value="range" />
          </v-radio-group>

          <v-row v-if="dateType === 'single'">
            <v-col cols="12">
              <v-text-field
                v-model="singleDate"
                label="Date"
                type="date"
                :rules="[(v) => !!v || 'Date is required']"
                :disabled="isImporting"
              />
            </v-col>
          </v-row>

          <v-row v-else>
            <v-col cols="6">
              <v-text-field
                v-model="startDate"
                label="Start Date"
                type="date"
                :rules="[(v) => !!v || 'Start date is required']"
                :disabled="isImporting"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="endDate"
                label="End Date"
                type="date"
                :rules="[(v) => !!v || 'End date is required']"
                :disabled="isImporting"
              />
            </v-col>
          </v-row>

          <v-select
            v-if="dateType === 'range'"
            v-model="frequency"
            :items="frequencyOptions"
            item-title="text"
            item-value="value"
            label="Frequency"
            :disabled="isImporting"
          />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
        <v-btn
          color="blue darken-1"
          text
          @click="startImport"
          :loading="isImporting"
          :disabled="!isFormValid"
          >Import</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
  <ProgressDialog
    v-model="showProgress"
    :progress="progress"
    :error="progressError"
    :title="'Importing FX Rates'"
    :current="current"
    :total="total"
    :currentMessage="currentMessage"
    :canStop="isImporting"
    @stop-import="stopImport"
  />
  <v-dialog v-model="showStopDialog" max-width="400px">
    <v-card>
      <v-card-title class="text-h5 pb-2">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        Import Stopped
      </v-card-title>
      <v-card-text>
        <p>The import process was stopped.</p>
        <v-divider class="my-3" />
        <v-row dense>
          <v-col cols="12">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="primary" size="40">
                    <v-icon dark>mdi-database-import</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ current }}
                </v-list-item-title>
                <v-list-item-subtitle
                  >FX rates imported before stopping</v-list-item-subtitle
                >
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="12">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="error" size="40">
                    <v-icon dark>mdi-cancel</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ total - current }}
                </v-list-item-title>
                <v-list-item-subtitle
                  >Remaining FX rates not imported</v-list-item-subtitle
                >
              </v-list-item>
            </v-card>
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" @click="closeStopDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <v-dialog v-model="showSuccessDialog" max-width="400px">
    <v-card>
      <v-card-title class="text-h5 pb-2">
        <v-icon color="success" class="mr-2">mdi-check-circle</v-icon>
        Import Completed
      </v-card-title>
      <v-card-text>
        <v-row dense>
          <v-col cols="12">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="primary" size="40">
                    <v-icon dark>mdi-database-import</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.totalImported }}
                </v-list-item-title>
                <v-list-item-subtitle
                  >Total FX rates imported</v-list-item-subtitle
                >
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="success" size="40">
                    <v-icon dark>mdi-plus-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.missingFilled }}
                </v-list-item-title>
                <v-list-item-subtitle>Missing filled</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="warning" size="40">
                    <v-icon dark>mdi-update</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.incompleteUpdated }}
                </v-list-item-title>
                <v-list-item-subtitle>Incomplete updated</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" @click="closeSuccessDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getFXImportStats, importFXRates, cancelFXImport } from '@/services/api'
import ProgressDialog from './ProgressDialog.vue'
import logger from '@/utils/logger'

export default {
  name: 'FXImportDialog',
  components: { ProgressDialog },
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'import-completed', 'refresh-table'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    })
    const stats = ref(null)
    const error = ref('')
    const importOption = ref(null)
    const importOptions = [
      { text: 'Import missing instances only', value: 'missing' },
      { text: 'Update incomplete instances only', value: 'incomplete' },
      { text: 'Import missing and update incomplete', value: 'both' },
    ]
    const isImporting = ref(false)
    const showProgress = ref(false)
    const progress = ref(0)
    const progressError = ref('')
    const current = ref(0)
    const total = ref(0)
    const currentMessage = ref('')
    const showSuccessDialog = ref(false)
    const importStats = ref({
      totalImported: 0,
      missingFilled: 0,
      incompleteUpdated: 0,
    })
    const abortController = ref(null)
    const showStopDialog = ref(false)

    const importType = ref('auto')
    const importTypes = [
      { text: 'Auto Import', value: 'auto' },
      { text: 'Manual Import', value: 'manual' },
    ]
    const dateType = ref('single')
    const singleDate = ref(null)
    const startDate = ref(null)
    const endDate = ref(null)
    const frequency = ref(null)
    const frequencyOptions = [
      { text: 'Daily', value: 'daily' },
      { text: 'Weekly', value: 'weekly' },
      { text: 'Monthly', value: 'monthly' },
      { text: 'Quarterly', value: 'quarterly' },
      { text: 'Yearly', value: 'yearly' },
    ]

    const isFormValid = computed(() => {
      if (importType.value === 'auto') {
        return !!importOption.value
      } else {
        if (dateType.value === 'single') {
          return !!singleDate.value
        } else {
          return !!startDate.value && !!endDate.value && !!frequency.value
        }
      }
    })

    const fetchStats = async () => {
      if (importType.value === 'auto') {
        try {
          stats.value = await getFXImportStats()
          logger.log('Unknown', 'Fetched stats:', stats.value)
        } catch (err) {
          error.value = 'Failed to fetch import statistics'
          logger.error('Unknown', 'Error fetching stats:', err)
        }
      } else {
        stats.value = null
      }
    }

    watch(importType, fetchStats)

    // watch(() => dialog.value, (newValue) => {
    //   if (newValue) {
    //     fetchStats()
    //   }
    // })

    const closeDialog = () => {
      dialog.value = false
      error.value = ''
      importOption.value = null
    }

    const startImport = async () => {
      isImporting.value = true
      showProgress.value = true
      progress.value = 0
      progressError.value = ''
      current.value = 0
      total.value = 0
      currentMessage.value = 'Starting import'
      abortController.value = new AbortController()
      try {
        dialog.value = false // Close the FXImportDialog
        let importData
        if (importType.value === 'auto') {
          importData = { import_option: importOption.value }
        } else {
          importData = {
            import_option: 'manual',
            date_type: dateType.value,
            single_date: singleDate.value,
            start_date: startDate.value,
            end_date: endDate.value,
            frequency: frequency.value,
          }
        }
        await importFXRates(importData, abortController.value.signal)
      } catch (err) {
        if (err.name === 'AbortError') {
          error.value = 'Import process was stopped'
        } else {
          error.value = 'Failed to start import process'
          logger.error('Unknown', err)
        }
        showProgress.value = false
      } finally {
        isImporting.value = false
        abortController.value = null
      }
    }

    const stopImport = async () => {
      if (abortController.value) {
        abortController.value.abort()
      }
      try {
        await cancelFXImport()
        currentMessage.value = 'Cancelling import'
        showProgress.value = false
        showStopDialog.value = true
      } catch (err) {
        logger.error('Unknown', 'Error cancelling import:', err)
        progressError.value = 'Failed to cancel import'
      }
    }

    const closeStopDialog = () => {
      showStopDialog.value = false
      closeDialog()
      emit('refresh-table') // Emit event to refresh the table
    }

    const handleProgress = (event) => {
      const data = event.detail
      if (data.status === 'initializing') {
        currentMessage.value = data.message
        total.value = data.total
      }
      if (data.status === 'updating') {
        progress.value = data.progress
        current.value = data.current
        currentMessage.value = data.message
      }
      if (data.status === 'completed') {
        showProgress.value = false
        importStats.value = data.stats // Assuming the backend sends stats in the completed event
        showSuccessDialog.value = true
        emit('import-completed', data)
      }
      if (data.status === 'cancelled') {
        showProgress.value = false
        showStopDialog.value = true
      }
    }

    const closeSuccessDialog = () => {
      showSuccessDialog.value = false
      fetchStats()
      closeDialog()
    }

    onMounted(() => {
      fetchStats()
      window.addEventListener('fxImportProgress', handleProgress)
    })

    onUnmounted(() => {
      window.removeEventListener('fxImportProgress', handleProgress)
    })

    logger.log('Unknown', 'Import options:', importOptions)

    return {
      dialog,
      stats,
      error,
      importOption,
      importOptions,
      isImporting,
      showProgress,
      progress,
      progressError,
      closeDialog,
      startImport,
      current,
      total,
      currentMessage,
      showSuccessDialog,
      importStats,
      closeSuccessDialog,
      stopImport,
      showStopDialog,
      closeStopDialog,
      importType,
      importTypes,
      dateType,
      singleDate,
      startDate,
      endDate,
      frequency,
      frequencyOptions,
      isFormValid,
    }
  },
}
</script>
