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
            <template v-for="field in formFields" :key="field.name">
              <v-select
                v-if="field.type === 'select'"
                v-model="formData[field.name]"
                :items="field.choices"
                item-title="text"
                item-value="value"
                :label="field.label"
                :error-messages="errors[field.name]"
                :disabled="isUpdating"
              ></v-select>
              <v-text-field
                v-else
                v-model="formData[field.name]"
                :label="field.label"
                :type="field.type"
                :error-messages="errors[field.name]"
                :disabled="isUpdating"
              ></v-text-field>
            </template>
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
import { useStore } from 'vuex'

export default {
  setup() {
    const store = useStore()
    const dialog = ref(false)
    const form = ref(null)
    const errors = ref({})
    const isUpdating = ref(false)
    const formFields = ref([])
    const formData = reactive({})

    const fetchSettingsData = async () => {
      try {
        const response = await getDashboardSettings()
        formFields.value = response.form_fields
        formFields.value.forEach(field => {
          if (field.type === 'select') {
            formData[field.name] = response[field.name].value
          } else {
            formData[field.name] = response[field.name]
          }
        })
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
          console.log('Settings updated successfully:', response.data)
          store.dispatch('updateEffectiveCurrentDate', formData.table_date)
          store.dispatch('triggerDataRefresh', {
            timespan: formData.table_date,
            page: 1,
            itemsPerPage: 25,
            search: '',
            sortBy: {}
          })
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
      formFields,
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