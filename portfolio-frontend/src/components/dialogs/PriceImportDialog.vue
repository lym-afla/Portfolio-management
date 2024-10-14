<template>
  <v-dialog v-model="dialog" max-width="800px">
    <v-card>
      <v-card-title>
        <span class="text-h5">Import Prices</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <v-autocomplete
            v-model="securities"
            :items="securitiesList"
            label="Securities"
            item-title="name"
            item-value="id"
            multiple
            clearable
            :disabled="brokers.length > 0"
            :error-messages="errors.securities"
            >
            <template v-slot:prepend-item>
              <v-list-item title="Select All" @click="toggleSelectAllSecurities">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="securitiesAllSelected"
                    :indeterminate="securitiesIndeterminate"
                  ></v-checkbox-btn>
                </template>
              </v-list-item>
              <v-divider class="mt-2"></v-divider>
            </template>
          </v-autocomplete>

          <v-autocomplete
            v-model="brokers"
            :items="brokersList"
            label="Brokers"
            item-title="name"
            item-value="id"
            multiple
            clearable
            :disabled="securities.length > 0"
            :error-messages="errors.brokers"
            >
            <template v-slot:prepend-item>
              <v-list-item title="Select All" @click="toggleSelectAllBrokers">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="brokersAllSelected"
                    :indeterminate="brokersIndeterminate"
                  ></v-checkbox-btn>
                </template>
              </v-list-item>
              <v-divider class="mt-2"></v-divider>
            </template>
          </v-autocomplete>

          <v-radio-group v-model="dateType" row>
            <v-radio label="Date Range" value="range"></v-radio>
            <v-radio label="Single Date" value="single"></v-radio>
          </v-radio-group>

          <template v-if="dateType === 'range'">
            <v-row>
              <v-col cols="12" sm="6">
                <div v-if="errors.startDate" class="text-caption text-error pl-6">
                  {{ errors.startDate }}
                </div>
                <v-date-picker 
                  v-model="startDate" 
                  label="Start Date"
                  :error-messages="errors.startDate"
                ></v-date-picker>
              </v-col>
              <v-col cols="12" sm="6">
                <div v-if="errors.endDate" class="text-caption text-error pl-6">
                  {{ errors.endDate }}
                </div>
                <v-date-picker 
                  v-model="endDate" 
                  label="End Date"
                  :error-messages="errors.endDate"
                ></v-date-picker>
              </v-col>
            </v-row>
            <v-select
              v-model="frequency"
              :items="frequencyChoices"
              item-title="text"
              item-value="value"
              label="Frequency"
              :error-messages="errors.frequency"
            ></v-select>
          </template>

          <template v-else>
            <div v-if="errors.singleDate" class="text-caption text-error pl-6">
                {{ errors.singleDate }}
            </div>
            <v-date-picker 
              v-model="singleDate" 
                label="Date"
                :error="!!errors.singleDate"
              ></v-date-picker>
          </template>

          <v-btn type="submit" color="primary" class="mt-4 w-100" :loading="isSubmitting">
            Import Prices
          </v-btn>
        </v-form>
      </v-card-text>
    </v-card>
  </v-dialog>

  <ProgressDialog
    v-model="showProgressDialog"
    :title="'Importing Prices'"
    :progress="progress"
    :error="generalError"
  />

  <v-dialog v-model="showSummaryDialog" max-width="800px">
    <v-card>
      <v-card-title>Import Summary</v-card-title>
      <v-card-text>
        <v-alert v-if="importSummary" type="success">
          <p>Total securities processed: {{ importSummary.totalSecurities }}</p>
          <p>Total dates processed: {{ importSummary.totalDates }}</p>
          <p>Start date: {{ importSummary.startDate }}</p>
          <p>End date: {{ importSummary.endDate }}</p>
          <p>Frequency: {{ importSummary.frequency }}</p>
        </v-alert>

        <v-table v-if="detailedSummary.length > 0">
          <thead>
            <tr>
              <th>Security</th>
              <th>Updated Dates</th>
              <th>Skipped Dates</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="security in detailedSummary" :key="security.name">
              <td>{{ security.name }}</td>
              <td>{{ security.updatedDates.length }}</td>
              <td>{{ security.skippedDates.length }}</td>
              <td>
                <v-tooltip v-if="security.errors.length > 0" bottom>
                  <template v-slot:activator="{ props }">
                    <v-icon v-bind="props" color="error">mdi-alert-circle</v-icon>
                  </template>
                  <span>{{ security.errors.join(', ') }}</span>
                </v-tooltip>
                <span v-else>None</span>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue darken-1" text @click="closeSummaryDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useForm, useField } from 'vee-validate'
import { importPrices, getPriceImportFormStructure } from '@/services/api'
import { format } from 'date-fns'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'PriceImportDialog',
  components: {
    ProgressDialog
  },
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'prices-imported'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })

    const dateType = ref('range')
    const securitiesList = ref([])
    const brokersList = ref([])
    const frequencyChoices = ref([])

    const { handleSubmit, resetForm, errors } = useForm({
      initialValues: {
        securities: [],
        brokers: [],
        startDate: null,
        endDate: null,
        frequency: null,
        singleDate: null,
      },
      validationSchema: {
        securities: (value) => {
          if (!value) return true; // Allow undefined during cleanup
          if (value.length === 0 && brokers.value.length === 0) {
            return 'Either securities or brokers must be selected'
          }
          return true
        },
        brokers: (value) => {
          if (!value) return true; // Allow undefined during cleanup
          if (value.length === 0 && securities.value.length === 0) {
            return 'Either securities or brokers must be selected'
          }
          return true
        },
        startDate: (value) => {
          if (dateType.value === 'range' && !value) {
            return 'Start date is required for date range'
          }
          return true
        },
        endDate: (value) => {
          if (dateType.value === 'range' && !value) {
            return 'End date is required for date range'
          }
          return true
        },
        frequency: (value) => {
          if (dateType.value === 'range' && !value) {
            return 'Frequency is required for date range'
          }
          return true
        },
        singleDate: (value) => {
          if (dateType.value === 'single' && !value) {
            return 'Date is required for single date import'
          }
          return true
        },
      },
    })

    const { value: securities, errorMessage: securitiesError } = useField('securities')
    const { value: brokers, errorMessage: brokersError } = useField('brokers')
    const { value: startDate, errorMessage: startDateError } = useField('startDate')
    const { value: endDate, errorMessage: endDateError } = useField('endDate')
    const { value: frequency, errorMessage: frequencyError } = useField('frequency')
    const { value: singleDate, errorMessage: singleDateError } = useField('singleDate')

    const generalError = ref('')
    const isSubmitting = ref(false)
    const isImporting = ref(false)
    const progress = ref(0)
    const importSummary = ref(null)
    const detailedSummary = ref([])
    const showProgressDialog = ref(false)
    const showSummaryDialog = ref(false)

    const { handleApiError } = useErrorHandler()

    const fetchFormStructure = async () => {
      try {
        const structure = await getPriceImportFormStructure()
        securitiesList.value = structure.securities
        brokersList.value = structure.brokers
        frequencyChoices.value = structure.frequency_choices
      } catch (error) {
        console.error('Error fetching form structure:', error)
        generalError.value = 'Failed to load form structure. Please try again.'
      }
    }

    const securitiesAllSelected = computed(() => {
      return securities.value.length === securitiesList.value.length
    })

    const securitiesIndeterminate = computed(() => {
      return securities.value.length > 0 && !securitiesAllSelected.value
    })

    const brokersAllSelected = computed(() => {
      return brokers.value.length === brokersList.value.length
    })

    const brokersIndeterminate = computed(() => {
      return brokers.value.length > 0 && !brokersAllSelected.value
    })

    const toggleSelectAllSecurities = () => {
      if (securitiesAllSelected.value) {
        securities.value = []
      } else {
        securities.value = securitiesList.value.map(s => s.id)
      }
    }

    const toggleSelectAllBrokers = () => {
      if (brokersAllSelected.value) {
        brokers.value = []
      } else {
        brokers.value = brokersList.value.map(b => b.id)
      }
    }

    const handleProgress = (event) => {
      console.log('Progress event received:', event)
      const data = event.detail
      if (data.status === 'progress') {
        progress.value = data.progress
        console.log('Updated progress:', progress.value)
      } else if (data.status === 'complete') {
        importSummary.value = {
          totalSecurities: data.details.length,
          totalDates: data.total_dates,
          startDate: data.start_date,
          endDate: data.end_date,
          frequency: data.frequency
        }
        detailedSummary.value = data.details.map(security => ({
          name: security.security_name,
          updatedDates: security.updated_dates || [],
          skippedDates: security.skipped_dates || [],
          errors: security.errors || []
        }))
        showProgressDialog.value = false
        showSummaryDialog.value = true
        emit('prices-imported', importSummary.value)
      } else if (data.status === 'error') {
        generalError.value = data.message
      }
    }

    const cleanupForm = () => {
      resetForm()
      securities.value = []
      brokers.value = []
      startDate.value = null
      endDate.value = null
      frequency.value = null
      singleDate.value = null
    }

    onMounted(() => {
      window.addEventListener('priceImportProgress', handleProgress)

      fetchFormStructure()
    })

    onBeforeUnmount(() => {
      window.removeEventListener('priceImportProgress', handleProgress)
      cleanupForm()
    })

    const submitForm = handleSubmit(async (values) => {

      // Check if there are any front-end validation errors
      if (Object.keys(errors.value).length > 0) {
        console.log('Front-end validation failed. Not submitting.')
        return
      }

      dialog.value = false
      showProgressDialog.value = true
      progress.value = 0
      importSummary.value = null
      detailedSummary.value = []
      generalError.value = ''

      try {
        // Prepare the data based on the date type
        const submitData = { 
          securities: values.securities,
          brokers: values.brokers,
          frequency: values.frequency
        }

        if (dateType.value === 'single') {
          if (values.singleDate) {
            submitData.single_date = format(new Date(values.singleDate), 'yyyy-MM-dd')
          }
        } else {
          if (values.startDate) {
            submitData.start_date = format(new Date(values.startDate), 'yyyy-MM-dd')
          }
          if (values.endDate) {
            submitData.end_date = format(new Date(values.endDate), 'yyyy-MM-dd')
          }
        }

        console.log('Submitting data:', submitData)
        
        await importPrices(submitData)
        resetForm()
      } catch (error) {
        console.error('Error importing prices:', error)
        handleApiError(error)
      } finally {
        if (!showSummaryDialog.value) {
          showProgressDialog.value = false
        }
      }
    })

    const closeSummaryDialog = () => {
      showSummaryDialog.value = false
      resetForm()
    }

    watch(() => props.modelValue, (newValue) => {
      if (!newValue) {
        cleanupForm()
      }
    })

    return {
      dialog,
      securities,
      brokers,
      dateType,
      startDate,
      endDate,
      frequency,
      singleDate,
      securitiesList,
      brokersList,
      frequencyChoices,
      securitiesError,
      brokersError,
      startDateError,
      endDateError,
      frequencyError,
      singleDateError,
      generalError,
      isSubmitting,
      isImporting,
      progress,
      importSummary,
      detailedSummary,
      securitiesAllSelected,
      securitiesIndeterminate,
      brokersAllSelected,
      brokersIndeterminate,
      toggleSelectAllSecurities,
      toggleSelectAllBrokers,
      submitForm,
      errors,
      showProgressDialog,
      showSummaryDialog,
      closeSummaryDialog,
    }
  }
}
</script>