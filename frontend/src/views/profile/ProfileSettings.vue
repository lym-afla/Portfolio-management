<template>
  <div>
    <v-card>
      <v-card-title>User Settings</v-card-title>
      <v-card-text>
        <v-progress-circular v-if="loading" indeterminate color="primary" />
        <v-form v-else @submit.prevent="saveSettings">
          <v-select
            v-model="settingsForm.default_currency"
            :items="currencyChoices"
            label="Default currency"
            :error-messages="fieldErrors.default_currency"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" :title="null">
                {{ item.title }}
              </v-list-item>
            </template>
          </v-select>

          <v-checkbox
            v-model="settingsForm.use_default_currency_where_relevant"
            label="Use default currency where relevant"
            :error-messages="fieldErrors.use_default_currency_where_relevant"
          />

          <v-select
            v-model="settingsForm.chart_frequency"
            :items="frequencyChoices"
            label="Chart frequency"
            :error-messages="fieldErrors.chart_frequency"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" :title="null">
                {{ item.title }}
              </v-list-item>
            </template>
          </v-select>

          <v-select
            v-model="settingsForm.chart_timeline"
            :items="timelineChoices"
            label="Chart timeline"
            :error-messages="fieldErrors.chart_timeline"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" :title="null">
                {{ item.title }}
              </v-list-item>
            </template>
          </v-select>

          <v-select
            v-model="settingsForm.NAV_barchart_default_breakdown"
            :items="navBreakdownChoices"
            label="Default NAV timeline breakdown"
            :error-messages="fieldErrors.NAV_barchart_default_breakdown"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" :title="null">
                {{ item.title }}
              </v-list-item>
            </template>
          </v-select>

          <v-text-field
            v-model.number="settingsForm.digits"
            type="number"
            label="Number of digits"
            :rules="[
              (v) =>
                (v >= 0 && v <= 6) ||
                'The value for digits must be between 0 and 6',
            ]"
            :error-messages="fieldErrors.digits"
          />

          <v-select
            v-model="settingsForm.selected_account"
            :items="accountChoices"
            item-title="title"
            item-value="value"
            label="Default Account Selection"
            :error-messages="fieldErrors.selected_account"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item
                v-if="item.raw.type === 'option'"
                v-bind="props"
                :title="null"
              >
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" />
              <v-list-subheader
                v-else-if="item.raw.type === 'header'"
                class="custom-subheader"
              >
                {{ item.raw.title }}
              </v-list-subheader>
            </template>
          </v-select>

          <v-card-actions>
            <v-btn type="submit" color="primary">Save Settings</v-btn>
          </v-card-actions>
        </v-form>
      </v-card-text>
    </v-card>

    <AccountGroupManager
      class="mt-4"
      @error="showErrorMessage"
      @success="showSuccessMessage"
    />

    <BrokerTokenManager
      class="mt-4"
      @error="showErrorMessage"
      @success="showSuccessMessage"
      @info="showInfoMessage"
    />

    <!-- Error Snackbar -->
    <v-snackbar v-model="snackbar" :timeout="3000" :color="snackbarColor">
      {{ snackbarMessage }}
      <template v-slot:actions>
        <v-btn color="white" text @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, provide, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import {
  getUserSettings,
  updateUserSettings,
  getSettingsChoices,
} from '@/services/api'
import { formatAccountChoices } from '@/utils/accountUtils'
import AccountGroupManager from '@/components/AccountGroupManager.vue'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'
import logger from '@/utils/logger'

const appStore = useAppStore()

const loading = ref(true)
const settingsForm = reactive({
  default_currency: '',
  use_default_currency_where_relevant: false,
  chart_frequency: '',
  chart_timeline: '',
  NAV_barchart_default_breakdown: '',
  digits: 0,
  selected_account: {
    type: 'all',
    id: null,
  },
})
const currencyChoices = ref([])
const frequencyChoices = ref([])
const timelineChoices = ref([])
const navBreakdownChoices = ref([])
const accountChoices = ref([])
const fieldErrors = reactive({
  default_currency: [],
  use_default_currency_where_relevant: [],
  chart_frequency: [],
  chart_timeline: [],
  NAV_barchart_default_breakdown: [],
  digits: [],
  selected_account: [],
})
const snackbar = ref(false)
const snackbarMessage = ref('')
const snackbarColor = ref('success')

const showSuccessMessage = (message) => {
  snackbarMessage.value = message
  snackbarColor.value = 'success'
  snackbar.value = true
}
const showErrorMessage = (message) => {
  snackbarMessage.value = message
  snackbarColor.value = 'error'
  snackbar.value = true
}
const showInfoMessage = (message) => {
  snackbarMessage.value = message
  snackbarColor.value = 'info'
  snackbar.value = true
}

// Provide error handling function for child components
provide('showError', (message) => {
  showErrorMessage(message)
})

const formatChoices = (choices) => {
  return choices.map((choice) => ({
    value: choice[0],
    title: choice[1],
  }))
}

const clearFieldErrors = () => {
  Object.keys(fieldErrors).forEach((field) => {
    fieldErrors[field] = []
  })
}

const handleFieldErrors = (errors) => {
  clearFieldErrors()
  Object.keys(errors).forEach((field) => {
    if (field in fieldErrors) {
      fieldErrors[field] = errors[field]
    }
  })
  showErrorMessage('Please correct the errors in the form.')
}

const loadData = async () => {
  try {
    loading.value = true
    const [settings, choices] = await Promise.all([
      getUserSettings(),
      getSettingsChoices(),
    ])

    // Format choices and set initial currency in store
    currencyChoices.value = formatChoices(choices.currency_choices)
    const selectedCurrencyOption = currencyChoices.value.find(
      (option) => option.value === settings.default_currency
    )
    if (selectedCurrencyOption) {
      appStore.setSelectedCurrency(selectedCurrencyOption.title)
    }

    // Format all choices first
    frequencyChoices.value = formatChoices(choices.frequency_choices)
    timelineChoices.value = formatChoices(choices.timeline_choices)
    navBreakdownChoices.value = formatChoices(choices.nav_breakdown_choices)
    accountChoices.value = formatAccountChoices(choices.account_choices)

    // Find the matching account option
    const matchingAccount = accountChoices.value.find(
      (option) =>
        option.type === 'option' &&
        option.value.type === settings.selected_account_type &&
        option.value.id === settings.selected_account_id
    )

    // Update form with settings
    Object.assign(settingsForm, settings, {
      selected_account: matchingAccount?.value || {
        type: 'all',
        id: null,
      },
    })
  } catch (error) {
    logger.error('Unknown', 'Error loading settings data:', error)
    showErrorMessage('Failed to load settings. Please try again.')
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  try {
    // Transform the data before sending
    const settingsToSave = {
      ...settingsForm,
      selected_account_type: settingsForm.selected_account.type,
      selected_account_id: settingsForm.selected_account.id,
    }
    delete settingsToSave.selected_account // Remove the combined field

    const response = await updateUserSettings(settingsToSave)
    if (response.success) {
      // Update store with new currency
      const selectedCurrencyOption = currencyChoices.value.find(
        (option) => option.value === settingsForm.default_currency
      )
      if (selectedCurrencyOption) {
        appStore.setSelectedCurrency(selectedCurrencyOption.title)
      }

      showSuccessMessage('Settings saved successfully')
    } else {
      handleFieldErrors(response.errors)
    }
  } catch (error) {
    logger.error('Unknown', 'Error saving settings:', error)
    showErrorMessage('Failed to save settings. Please try again.')
  }
}

onMounted(async () => {
  logger.log('Unknown', 'ProfileSettings component mounted')
  await loadData()
})
</script>

<style scoped>
.custom-subheader {
  font-weight: bold;
  font-size: 1.1em;
  color: #000000;
  padding-top: 12px;
  padding-bottom: 12px;
  background-color: #f5f5f5;
}
</style>
