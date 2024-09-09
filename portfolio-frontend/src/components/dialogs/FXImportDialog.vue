<template>
    <v-dialog v-model="dialog" max-width="600px">
      <v-card>
        <v-card-title class="text-h5 pb-2">
          Import FX Rates
        </v-card-title>
        <v-card-text>
          <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
          
          <v-row v-if="stats" class="mb-4">
            <v-col cols="12" sm="4">
                <v-card elevation="2" class="pa-2 text-center">
                    <v-icon color="primary" size="large" class="mb-2">mdi-calendar-range</v-icon>
                    <v-card-title class="text-h6">{{ stats.total_dates }}</v-card-title>
                    <v-card-subtitle>Total Dates</v-card-subtitle>
                </v-card>
            </v-col>
            <v-col cols="12" sm="4">
              <v-card elevation="2" class="pa-2 text-center">
                <v-icon color="error" size="large" class="mb-2">mdi-currency-usd-off</v-icon>
                <v-card-title class="text-h6">{{ stats.missing_instances }}</v-card-title>
                <v-card-subtitle>Missing FX</v-card-subtitle>
              </v-card>
            </v-col>
            <v-col cols="12" sm="4">
              <v-card elevation="2" class="pa-2 text-center">
                <v-icon color="warning" size="large" class="mb-2">mdi-currency-usd</v-icon>
                <v-card-title class="text-h6">{{ stats.incomplete_instances }}</v-card-title>
                <v-card-subtitle>Incomplete FX</v-card-subtitle>
              </v-card>
            </v-col>
          </v-row>

          <v-select
            v-model="importOption"
            :items="importOptions"
            item-title="text"
            item-value="value"
            label="Import Option"
            :disabled="isImporting"
          ></v-select>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
          <v-btn color="blue darken-1" text @click="startImport" :loading="isImporting" :disabled="!importOption">Import</v-btn>
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
    />
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
                  <v-list-item-subtitle>Total FX rates imported</v-list-item-subtitle>
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
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="closeSuccessDialog">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </template>
  
  <script>
  import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
  import { getFXImportStats, importFXRates } from '@/services/api'
  import ProgressDialog from './ProgressDialog.vue'
  
  export default {
    name: 'FXImportDialog',
    components: { ProgressDialog },
    props: {
      modelValue: Boolean,
    },
    emits: ['update:modelValue', 'import-completed'],
    setup(props, { emit }) {
      const dialog = computed({
        get: () => props.modelValue,
        set: (value) => emit('update:modelValue', value)
      })
      const stats = ref(null)
      const error = ref('')
      const importOption = ref(null)
      const importOptions = [
        { text: 'Import missing instances only', value: 'missing' },
        { text: 'Update incomplete instances only', value: 'incomplete' },
        { text: 'Import missing and update incomplete', value: 'both' }
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
        incompleteUpdated: 0
      })

      const fetchStats = async () => {
        try {
          stats.value = await getFXImportStats()
          console.log('Fetched stats:', stats.value)
        } catch (err) {
          error.value = 'Failed to fetch import statistics'
          console.error('Error fetching stats:', err)
        }
      }

      watch(() => dialog.value, (newValue) => {
        if (newValue) {
          fetchStats()
        }
      })

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
        try {
          dialog.value = false // Close the FXImportDialog
          await importFXRates(importOption.value)
        } catch (err) {
          error.value = 'Failed to start import process'
          console.error(err)
          showProgress.value = false
        } finally {
          isImporting.value = false
        }
      }

      const handleProgress = (event) => {
        const data = event.detail
        if (data.progress) {
          progress.value = data.progress
          current.value = data.current
          total.value = data.total
          currentMessage.value = data.message
        }
        if (data.status === 'completed') {
          showProgress.value = false
          importStats.value = data.stats // Assuming the backend sends stats in the completed event
          showSuccessDialog.value = true
          emit('import-completed', data)
        }
      }

      const closeSuccessDialog = () => {
        showSuccessDialog.value = false
        closeDialog()
      }

      onMounted(() => {
        window.addEventListener('fxImportProgress', handleProgress)
      })

      onUnmounted(() => {
        window.removeEventListener('fxImportProgress', handleProgress)
      })

      fetchStats()

      console.log('Import options:', importOptions)

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
        closeSuccessDialog
      }
    }
  }
  </script>