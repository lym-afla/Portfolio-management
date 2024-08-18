<template>
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
          v-model="settingsForm.custom_brokers"
          :items="brokerChoices"
          label="Brokers"
          :error-messages="fieldErrors.custom_brokers"
        >
          <template v-slot:item="{ item, props }">
            <v-list-item v-if="item.raw.type === 'option'" v-bind="props" :title="null">
              {{ item.title }}
            </v-list-item>
            <v-divider v-else-if="item.raw.type === 'divider'" />
            <v-list-subheader v-else-if="item.raw.type === 'header'" class="custom-subheader">
              {{ item.title }}
            </v-list-subheader>
          </template>
        </v-select>
        
        <v-card-actions>
          <v-btn type="submit" color="primary">Save Settings</v-btn>
        </v-card-actions>
      </v-form>
    </v-card-text>

    <!-- Error Snackbar -->
    <v-snackbar v-model="snackbar" :timeout="3000" :color="snackbarColor">
      {{ snackbarMessage }}
      <template v-slot:actions>
        <v-btn color="white" text @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </v-card>
</template>

<script>
import { getUserSettings, updateUserSettings, getSettingsChoices } from '@/services/api'
import { formatBrokerChoices } from '@/utils/brokerUtils'

export default {
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
        custom_brokers: '',
      },
      currencyChoices: [],
      frequencyChoices: [],
      timelineChoices: [],
      navBreakdownChoices: [],
      brokerChoices: [],
      fieldErrors: {
        default_currency: [],
        use_default_currency_where_relevant: [],
        chart_frequency: [],
        chart_timeline: [],
        NAV_barchart_default_breakdown: [],
        digits: [],
        custom_brokers: [],
      },
      snackbar: false,
      snackbarMessage: '',
    }
  },
  computed: {
    snackbarColor() {
      return this.snackbarMessage.toLowerCase().includes('error') ? 'error' : 'success';
    }
  },
  async mounted() {
    await this.loadData();
  },
  methods: {
    async loadData() {
      try {
        await Promise.all([
          this.fetchSettings(),
          this.fetchChoices()
        ]);
        this.loading = false;
      } catch (error) {
        console.error('Error loading data:', error);
        this.showErrorMessage('Failed to load settings. Please refresh the page.');
        this.loading = false;
      }
    },
    async fetchSettings() {
      const response = await getUserSettings();
      this.settingsForm = response;
    },
    async fetchChoices() {
      const response = await getSettingsChoices();
      this.currencyChoices = this.formatChoices(response.currency_choices);
      this.frequencyChoices = this.formatChoices(response.frequency_choices);
      this.timelineChoices = this.formatChoices(response.timeline_choices);
      this.navBreakdownChoices = this.formatChoices(response.nav_breakdown_choices);
      this.brokerChoices = formatBrokerChoices(response.broker_choices);
    },
    formatChoices(choices) {
      return choices.map(choice => ({
        value: choice[0],
        title: choice[1]
      }));
    },
    async saveSettings() {
      try {
        console.log('Sending settings:', this.settingsForm);
        const response = await updateUserSettings(this.settingsForm);
        console.log('Settings saved successfully:', response);
        this.showSuccessMessage('Settings saved successfully');
        this.clearFieldErrors();
      } catch (error) {
        console.error('Error saving settings:', error.response?.data || error.message);
        if (error.response && error.response.data && error.response.data.errors) {
          this.handleFieldErrors(error.response.data.errors);
        } else {
          this.showErrorMessage('Failed to save settings. Please try again.');
        }
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
      this.snackbar = true;
    },
    showErrorMessage(message) {
      this.snackbarMessage = message;
      this.snackbar = true;
    },
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