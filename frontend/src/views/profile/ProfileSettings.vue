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
                (v >= 0 && v <= 9) ||
                'The value for digits must be between 0 and 9',
            ]"
            :error-messages="fieldErrors.digits"
          />

          <v-select
            v-model="accountSelectionModel"
            :items="accountChoices"
            item-title="title"
            item-value="value"
            label="Default Account Selection"
            :error-messages="accountFieldMessages"
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
            <v-btn type="submit" color="primary" :disabled="!canSave">
              Save Settings
            </v-btn>
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
import { ref, reactive, computed, provide, onMounted } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import {
  getUserSettings,
  updateUserSettings,
  getSettingsChoices,
} from '@/services/api'
import { committedAccountLabel, formatAccountChoices } from '@/utils/accountUtils'
import AccountGroupManager from '@/components/AccountGroupManager.vue'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'
import logger from '@/utils/logger'

// Same shapes the backend serializer and the context store accept
// (services/api/context.ts selectionFrom): the all selection with a null id,
// or account/broker/group with a positive integer id. Anything else is an
// unresolved form state, never an All accounts default.
const isValidAccountIdentity = (identity) =>
  !!identity &&
  ((identity.type === 'all' && identity.id === null) ||
    (['account', 'broker', 'group'].includes(identity.type) &&
      Number.isInteger(identity.id) &&
      identity.id > 0))

const loading = ref(true)
// Only a fully successful settings+choices load may enable saving; a failed
// load must never offer a write that would replace the unknown saved state.
const dataLoaded = ref(false)
const settingsForm = reactive({
  default_currency: '',
  use_default_currency_where_relevant: false,
  chart_frequency: '',
  chart_timeline: '',
  NAV_barchart_default_breakdown: '',
  digits: 0,
  // The saved account identity from the settings response, kept separately
  // from the select's display model. Null while unresolved.
  selected_account: null,
})
const currencyChoices = ref([])
const frequencyChoices = ref([])
const timelineChoices = ref([])
const navBreakdownChoices = ref([])
const rawAccountChoices = ref([])
const accountChoices = computed(() =>
  formatAccountChoices(rawAccountChoices.value)
)
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

const matchingAccountOption = computed(() => {
  const identity = settingsForm.selected_account
  if (!isValidAccountIdentity(identity)) return undefined
  return accountChoices.value.find(
    (option) =>
      option.type === 'option' &&
      option.value.type === identity.type &&
      option.value.id === identity.id
  )
})

const accountResolved = computed(() => !!matchingAccountOption.value)

// Safe label for the saved identity while it matches no selectable option:
// the matching title, "All accounts" for a valid all selection, "Unavailable"
// otherwise. The raw identity object would render as [object Object].
const savedAccountLabel = computed(() =>
  committedAccountLabel(rawAccountChoices.value, settingsForm.selected_account || {})
)

const accountAvailabilityMessage = computed(() => {
  if (!dataLoaded.value || accountResolved.value) return ''
  if (!isValidAccountIdentity(settingsForm.selected_account)) {
    return 'Your saved account selection is unavailable. Choose an available account selection before saving.'
  }
  if (rawAccountChoices.value.length === 0) {
    return 'Account choices are unavailable. Reload settings before saving.'
  }
  return 'Your saved account selection is unavailable. Choose an available account selection before saving.'
})

const accountFieldMessages = computed(() => [
  ...fieldErrors.selected_account,
  ...(accountAvailabilityMessage.value ? [accountAvailabilityMessage.value] : []),
])

// The select's display model: the matched option's own value while resolved
// (Vuetify then renders its title), otherwise the safe label STRING — an
// unmatched identity object would surface as [object Object] in both the
// visible selection and the underlying input value. Selections are accepted
// only when they are actual selectable option values, so the safe display
// string can never enter the form identity or a transport payload.
const accountSelectionModel = computed({
  get: () => matchingAccountOption.value?.value ?? savedAccountLabel.value,
  set: (value) => {
    const match = accountChoices.value.find(
      (option) =>
        option.type === 'option' &&
        option.value?.type === value?.type &&
        option.value?.id === value?.id
    )
    if (match) {
      settingsForm.selected_account = { type: match.value.type, id: match.value.id }
    }
  },
})

const canSave = computed(
  () => dataLoaded.value && accountResolved.value
)

const loadData = async () => {
  try {
    loading.value = true
    const [settings, choices] = await Promise.all([
      getUserSettings(),
      getSettingsChoices(),
    ])

    currencyChoices.value = formatChoices(choices.currency_choices)

    // Format all choices first
    frequencyChoices.value = formatChoices(choices.frequency_choices)
    timelineChoices.value = formatChoices(choices.timeline_choices)
    navBreakdownChoices.value = formatChoices(choices.nav_breakdown_choices)
    rawAccountChoices.value = Array.isArray(choices.account_choices)
      ? choices.account_choices
      : []

    // The settings response is the authority for this form's identity: keep
    // the saved selection exactly as returned when structurally valid, even
    // when no option matches — a missing selection must surface as
    // unresolved, never silently broaden to All accounts.
    const savedIdentity = {
      type: settings.selected_account_type,
      id: settings.selected_account_id,
    }
    Object.assign(settingsForm, settings, {
      selected_account: isValidAccountIdentity(savedIdentity) ? savedIdentity : null,
    })
    dataLoaded.value = true
  } catch (error) {
    logger.error('Unknown', 'Error loading settings data:', error)
    showErrorMessage('Failed to load settings. Please try again.')
    dataLoaded.value = false
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  // The disabled button cannot stop a form submission through Enter, so the
  // handler itself must guard before either existing write.
  if (!canSave.value) return
  try {
    const context = usePortfolioContextStore()
    const patch = {
      accountSelection: { type: settingsForm.selected_account.type, id: settingsForm.selected_account.id },
      effectiveCurrentDate: context.committed.effectiveCurrentDate,
      currency: settingsForm.default_currency,
      digits: Number(settingsForm.digits),
    }
    // The profile endpoint still owns chart/display preferences. Financial
    // context fields go through the same serialized confirmation as the header.
    const settingsToSave = { ...settingsForm }
    for (const key of ['selected_account', 'selected_account_type', 'selected_account_id', 'default_currency', 'digits']) delete settingsToSave[key]
    const response = await updateUserSettings(settingsToSave)
    if (response.success) {
      await context.changeContext(patch)
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
