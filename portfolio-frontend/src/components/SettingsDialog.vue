<template>
  <div>
    <v-btn icon @click="openDialog">
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
              v-model.number="formData.digits"
              label="Number of Digits"
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
            Save
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { getDashboardSettings, updateDashboardSettings } from '@/services/api'

export default {
  setup() {
    const dialog = ref(false)
    const form = ref(null)
    const errors = ref({})
    const currencyChoices = ref([])
    const isUpdating = ref(false)

    const formData = reactive({
      default_currency: '',
      digits: 0,
      table_date: '',
    })

    const fetchSettingsData = async () => {
      try {
        const response = await getDashboardSettings()
        formData.default_currency = response.default_currency
        formData.digits = response.digits
        formData.table_date = response.table_date
        currencyChoices.value = response.currency_choices
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
        const response = await updateDashboardSettings(formData)
        if (response.success) {
          closeDialog()
          window.location.reload()
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