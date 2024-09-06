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
        <v-alert v-if="generalError" type="error" class="mt-4">
          {{ generalError }}
        </v-alert>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useForm, useField } from 'vee-validate'
import { importPrices, getPriceImportFormStructure } from '@/services/api'
import { format } from 'date-fns'

export default {
  name: 'PriceImportDialog',
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'prices-imported'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })

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
          if (value.length === 0 && brokers.value.length === 0) {
            return 'Either securities or brokers must be selected'
          }
          return true
        },
        brokers: (value) => {
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

    const dateType = ref('range')
    const securitiesList = ref([])
    const brokersList = ref([])
    const frequencyChoices = ref([])
    const generalError = ref('')
    const isSubmitting = ref(false)

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

    onMounted(() => {
      fetchFormStructure()
    })

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

    const submitForm = handleSubmit(async (values) => {
      console.log('Submitting form with values:', values)
      console.log('Current errors:', errors.value)

      // Check if there are any front-end validation errors
      if (Object.keys(errors.value).length > 0) {
        console.log('Front-end validation failed. Not submitting.')
        return
      }

      isSubmitting.value = true
      generalError.value = ''
      // Clear previous errors
      Object.keys(errors.value).forEach(key => {
        errors.value[key] = ''
      })

      try {
        // Prepare the data based on the date type
        const submitData = { ...values }
        if (dateType.value === 'single') {
          // If it's a single date, remove the date range fields and format the single date
          delete submitData.startDate
          delete submitData.endDate
          delete submitData.frequency
          if (submitData.singleDate) {
            submitData.single_date = format(new Date(submitData.singleDate), 'yyyy-MM-dd')
          }
        } else {
          // If it's a date range, remove the single date field and format start and end dates
          delete submitData.singleDate
          if (submitData.startDate) {
            submitData.start_date = format(new Date(submitData.startDate), 'yyyy-MM-dd')
          }
          if (submitData.endDate) {
            submitData.end_date = format(new Date(submitData.endDate), 'yyyy-MM-dd')
          }
        }

        console.log('Submitting data:', submitData)  // Add this line for debugging

        const response = await importPrices(submitData)
        emit('prices-imported', response)
        dialog.value = false
        resetForm()
      } catch (error) {
        console.error('Error importing prices:', error)
        if (typeof error === 'object') {
          if (error.non_field_errors) {
            generalError.value = error.non_field_errors[0]
          } else {
            // Handle field-specific errors
            Object.keys(error).forEach(key => {
              if (Array.isArray(error[key])) {
                errors.value[key] = error[key][0]
              } else {
                errors.value[key] = error[key]
              }
            })
          }
        } else {
          generalError.value = error.toString()
        }
      } finally {
        isSubmitting.value = false
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
      securitiesAllSelected,
      securitiesIndeterminate,
      brokersAllSelected,
      brokersIndeterminate,
      toggleSelectAllSecurities,
      toggleSelectAllBrokers,
      submitForm,
      errors,
    }
  }
}
</script>