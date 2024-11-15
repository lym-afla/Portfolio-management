<template>
  <div>
    <v-btn icon @click="openDialog" elevation="2">
      <v-icon>mdi-cog</v-icon>
    </v-btn>

    <v-dialog v-model="dialog" max-width="400px" persistent>
      <v-card>
        <v-card-title class="text-h5">
          Settings
        </v-card-title>
        <v-card-text>
          <v-form @submit.prevent="saveSettings" ref="form">
            <v-select
              v-model="formData.default_currency"
              :items="currencyChoices"
              item-title="text"
              item-value="value"
              label="Currency"
              :error-messages="errors.default_currency"
              :disabled="isUpdating"
            ></v-select>
            <v-text-field
              v-model="formData.digits"
              label="Number of digits"
              type="number"
              :error-messages="errors.digits"
              :disabled="isUpdating"
            ></v-text-field>
            <v-text-field
              v-model="formData.table_date"
              label="Date"
              type="date"
              :error-messages="errors.table_date"
              :disabled="isUpdating"
            ></v-text-field>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="closeDialog" :disabled="isUpdating">Close</v-btn>
          <v-btn color="blue-darken-1" variant="text" @click="saveSettings" :loading="isUpdating" :disabled="isUpdating">
            Update
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { getDashboardSettings, updateDashboardSettings } from '@/services/api'
import { useStore } from 'vuex'
import { calculateDateRangeFromTimespan } from '@/utils/dateUtils'

export default {
  setup() {
    const store = useStore()
    const dialog = ref(false)
    const form = ref(null)
    const errors = ref({})
    const isUpdating = ref(false)
    const currencyChoices = ref([])
    const formData = reactive({
      default_currency: '',
      digits: 0,
      table_date: '',
    })

    const fetchSettingsData = async () => {
      try {
        const response = await getDashboardSettings()
        console.log('[SettingsDialog] Getting dashboard settings:', response)
        
        // Update formData with settings
        Object.assign(formData, response.settings)
        
        // Format currency choices
        currencyChoices.value = response.choices.default_currency.map(([value, text]) => ({ value, text }))

        // Find the list in choices.default_currency where the first element equals settings.default_currency
        const selectedCurrency = response.choices.default_currency.find(([value]) => value === response.settings.default_currency)
        console.log('[SettingsDialog] Selected currency:', selectedCurrency)
        // Set the currency in the store to the second element of the found list
        if (selectedCurrency && store.state.selectedCurrency !== selectedCurrency[1] ) {
          store.commit('SET_SELECTED_CURRENCY', selectedCurrency[1])
        }

      } catch (error) {
        console.error('Failed to fetch settings data:', error)
      }
    }

    const openDialog = () => {
      dialog.value = true
      fetchSettingsData()
    }

    const closeDialog = () => {
      dialog.value = false
      clearErrors()
    }

    const clearErrors = () => {
      errors.value = {}
    }

    const saveSettings = async () => {
      try {
        clearErrors()
        isUpdating.value = true
        console.log('[SettingsDialog] Sending formData:', formData)
        const response = await updateDashboardSettings(formData)
        if (response.success) {
          console.log('Settings updated successfully:', response)
          
          // Update store with new currency
          const selectedCurrencyOption = currencyChoices.value.find(
            option => option.value === formData.default_currency
          )
          if (selectedCurrencyOption) {
            store.commit('SET_SELECTED_CURRENCY', selectedCurrencyOption.text)
          }

          store.dispatch('updateEffectiveCurrentDate', response.table_date)
          
          // Get the current state from the store
          const currentState = store.state
          console.log('[SettingsDialog] Current state:', currentState)

          // Calculate new date range based on the new effective date
          const dateRange = calculateDateRangeFromTimespan(currentState.tableSettings.timespan, response.table_date)
          
          // Update table settings and trigger data refresh
          store.dispatch('updateTableSettings', {
            timespan: currentState.tableSettings.timespan,
            dateFrom: dateRange.dateFrom,
            dateTo: dateRange.dateTo,
            page: currentState.tableSettings.page,
            itemsPerPage: currentState.tableSettings.itemsPerPage,
            search: currentState.tableSettings.search,
            sortBy: currentState.tableSettings.sortBy
          })
          store.dispatch('triggerDataRefresh')
          
          closeDialog()
        } else {
          handleErrors(response.errors)
        }
      } catch (error) {
        console.error('Failed to save settings:', error)
        if (error.response && error.response.data && error.response.data.errors) {
          handleErrors(error.response.data.errors)
        } else {
          errors.value = { general: ['An unexpected error occurred. Please try again.'] }
        }
      } finally {
        isUpdating.value = false
      }
    }

    const handleErrors = (errorData) => {
      Object.keys(errorData).forEach(field => {
        if (Array.isArray(errorData[field])) {
          errors.value[field] = errorData[field]
        } else {
          errors.value[field] = [errorData[field]]
        }
      })
    }

    onMounted(fetchSettingsData)

    return {
      dialog,
      formData,
      currencyChoices,
      form,
      errors,
      openDialog,
      closeDialog,
      saveSettings,
      isUpdating
    }
  }
}
</script>