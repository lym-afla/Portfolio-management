<template>
  <div>
    <v-card>
      <v-card-title>User Settings</v-card-title>
      <v-card-text>
        <v-progress-circular
          v-if="loading"
          indeterminate
          color="primary"
        ></v-progress-circular>
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
          ></v-checkbox>
          
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
            :rules="[v => v >= 0 && v <= 6 || 'The value for digits must be between 0 and 6']"
            :error-messages="fieldErrors.digits"
          ></v-text-field>
          
          <v-select
            v-model="settingsForm.selected_account"
            :items="accountChoices"
            item-title="title"
            item-value="value"
            label="Default Account Selection"
            :error-messages="fieldErrors.selected_account"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-if="item.raw.type === 'option'" v-bind="props" :title="null">
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" />
              <v-list-subheader v-else-if="item.raw.type === 'header'" class="custom-subheader">
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

<script>
import { provide } from 'vue'
import { useStore } from 'vuex'
import { getUserSettings, updateUserSettings, getSettingsChoices } from '@/services/api'
import { formatAccountChoices } from '@/utils/accountUtils'
import AccountGroupManager from '@/components/AccountGroupManager.vue'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'

export default {
  components: {
    AccountGroupManager,
    BrokerTokenManager
  },

  setup() {
    const store = useStore()
    // Provide error handling function for child components
    provide('showError', (message) => {
      this.showErrorMessage(message)
    })
    return { store }
  },

  data() {
    return {
      loading: true,
      settingsForm: {
        default_currency: '',
        use_default_currency_where_relevant: false,
        chart_frequency: '',
        chart_timeline: '',
        NAV_barchart_default_breakdown: '',
        digits: 0,
        selected_account: {
          type: 'all',
          id: null
        },
      },
      currencyChoices: [],
      frequencyChoices: [],
      timelineChoices: [],
      navBreakdownChoices: [],
      accountChoices: [],
      fieldErrors: {
        default_currency: [],
        use_default_currency_where_relevant: [],
        chart_frequency: [],
        chart_timeline: [],
        NAV_barchart_default_breakdown: [],
        digits: [],
        selected_account: [],
      },
      snackbar: false,
      snackbarMessage: '',
      snackbarColor: 'success',
    }
  },

  async mounted() {
    console.log('ProfileSettings component mounted')
    await this.loadData();
  },

  methods: {
    async loadData() {
      try {
        this.loading = true
        const [settings, choices] = await Promise.all([
          getUserSettings(),
          getSettingsChoices()
        ])
        
        // Format choices and set initial currency in store
        this.currencyChoices = this.formatChoices(choices.currency_choices)
        const selectedCurrencyOption = this.currencyChoices.find(
          option => option.value === settings.default_currency
        )
        if (selectedCurrencyOption) {
          this.store.commit('SET_SELECTED_CURRENCY', selectedCurrencyOption.title)
        }

        // Format all choices first
        this.frequencyChoices = this.formatChoices(choices.frequency_choices)
        this.timelineChoices = this.formatChoices(choices.timeline_choices)
        this.navBreakdownChoices = this.formatChoices(choices.nav_breakdown_choices)
        this.accountChoices = formatAccountChoices(choices.account_choices)

        // Find the matching account option
        const matchingAccount = this.accountChoices.find(
          option => option.type === 'option' && 
                    option.value.type === settings.selected_account_type && 
                    option.value.id === settings.selected_account_id
        )

        // Update form with settings
        this.settingsForm = {
          ...settings,
          selected_account: matchingAccount?.value || {
            type: 'all',
            id: null
          }
        }

      } catch (error) {
        console.error('Error loading settings data:', error)
        this.showErrorMessage('Failed to load settings. Please try again.')
      } finally {
        this.loading = false
      }
    },
    formatChoices(choices) {
      return choices.map(choice => ({
        value: choice[0],
        title: choice[1]
      }));
    },
    async saveSettings() {
      try {
        // Transform the data before sending
        const settingsToSave = {
          ...this.settingsForm,
          selected_account_type: this.settingsForm.selected_account.type,
          selected_account_id: this.settingsForm.selected_account.id,
        }
        delete settingsToSave.selected_account  // Remove the combined field

        const response = await updateUserSettings(settingsToSave)
        if (response.success) {
          // Update store with new currency
          const selectedCurrencyOption = this.currencyChoices.find(
            option => option.value === this.settingsForm.default_currency
          )
          if (selectedCurrencyOption) {
            this.store.commit('SET_SELECTED_CURRENCY', selectedCurrencyOption.title)
          }

          this.showSuccessMessage('Settings saved successfully')
        } else {
          this.handleFieldErrors(response.errors)
        }
      } catch (error) {
        console.error('Error saving settings:', error)
        this.showErrorMessage('Failed to save settings. Please try again.')
      }
    },
    handleFieldErrors(errors) {
      this.clearFieldErrors();
      Object.keys(errors).forEach(field => {
        if (field in this.fieldErrors) {
          this.fieldErrors[field] = errors[field];
        }
      });
      this.showErrorMessage('Please correct the errors in the form.');
    },
    clearFieldErrors() {
      Object.keys(this.fieldErrors).forEach(field => {
        this.fieldErrors[field] = [];
      });
    },
    showSuccessMessage(message) {
      this.snackbarMessage = message;
      this.snackbarColor = 'success';
      this.snackbar = true;
    },
    showErrorMessage(message) {
      this.snackbarMessage = message;
      this.snackbarColor = 'error';
      this.snackbar = true;
    },
    showInfoMessage(message) {
      this.snackbarMessage = message;
      this.snackbarColor = 'info';
      this.snackbar = true;
    }
  }
}
</script>

<style scoped>
.custom-subheader {
  font-weight: bold;
  font-size: 1.1em;
  color: #000000;
  padding-top: 12px;
  padding-bottom: 12px;
  background-color: #F5F5F5;
}
</style>