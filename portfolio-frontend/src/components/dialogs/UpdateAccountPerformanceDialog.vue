<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>Update Account Performance</v-card-title>
      <v-card-text>
        <v-form ref="form" @submit.prevent="submitForm">
          <v-select
            v-model="selectedAccount"
            :items="accountOptions"
            item-title="title"
            item-value="value"
            label="Account Selection"
            :error-messages="errorMessages['selection_account_type']"
            required
            class="mb-4"
            @update:model-value="handleAccountChange"
          >
            <template v-slot:item="{ props, item }">
              <v-list-item 
                v-if="item.raw.type === 'option'" 
                v-bind="props" 
                :title="null"
              >
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
              <v-list-subheader v-else-if="item.raw.type === 'header'" class="custom-subheader">
                {{ item.raw.title }}
              </v-list-subheader>
            </template>
          </v-select>

          <v-select
            v-model="formData.currency"
            :items="currencyOptions"
            item-title="text"
            item-value="value"
            label="Currency"
            :error-messages="errorMessages['currency']"
            required
            class="mb-4"
          />

          <v-select
            v-model="formData.is_restricted"
            :items="restrictedOptions"
            item-title="text"
            item-value="value"
            label="Restriction"
            :error-messages="errorMessages['is_restricted']"
            required
          />

          <v-checkbox
            v-model="formData.skip_existing_years"
            label="Skip existing years"
          />
        </v-form>

        <v-alert
          v-if="generalError"
          type="error"
          class="mt-4"
        >
          {{ generalError }}
        </v-alert>
      </v-card-text>

      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
        <v-btn
          color="blue darken-1"
          text
          @click="submitForm"
          :loading="loading"
          :disabled="loading"
        >
          Update
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, watch } from 'vue'
import { getAccountPerformanceFormData } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useStore } from 'vuex'
import { formatAccountChoices } from '@/utils/accountUtils'
// import { updateAccountPerformance } from '@/services/api'
import axiosInstance from '@/config/axiosConfig'

export default {
  name: 'UpdateAccountPerformanceDialog',
  props: {
    modelValue: Boolean
  },
  emits: ['update:modelValue', 'update-started', 'update-error'],
  setup(props, { emit }) {
    const store = useStore()
    const form = ref(null)
    const loading = ref(false)
    const generalError = ref('')
    const accountOptions = ref([])
    const currencyOptions = ref([])
    const restrictedOptions = ref([])
    const selectedAccount = ref(null)

    const selectedCurrency = computed(() => store.state.selectedCurrency)

    const formData = ref({
      selection_account_type: '',
      selection_account_id: null,
      currency: '',
      is_restricted: '',
      skip_existing_years: false
    })
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })
    
    // Get current account selection from store
    const currentStoreSelection = computed(() => store.state.accountSelection)

    const { handleApiError } = useErrorHandler()
    const fetchFormData = async () => {
      try {
        const data = await getAccountPerformanceFormData()
        accountOptions.value = formatAccountChoices(data.account_choices)
        currencyOptions.value = Object.entries(data.currency_choices).map(([value, text]) => ({ value, text }))
        restrictedOptions.value = Object.entries(data.is_restricted_choices).map(([value, text]) => ({ value, text }))

        // Set initial account selection
        const matchingOption = accountOptions.value.find(
          option => option.type === 'option' && 
          option.value.type === currentStoreSelection.value.type && 
          option.value.id === currentStoreSelection.value.id
        )
        
        if (matchingOption) {
          selectedAccount.value = matchingOption.value
          handleAccountChange(matchingOption.value)
        }

        // Set initial currency using the currency code (value), not the display text
        const currencyOption = currencyOptions.value.find(option => option.text === selectedCurrency.value)
        formData.value.currency = currencyOption?.value // Use the currency code
      } catch (error) {
        handleApiError(error)
        emit('update-error', 'Failed to load form data')
      }
    }

    const handleAccountChange = (newValue) => {
      if (newValue) {
        formData.value.selection_account_type = newValue.type
        formData.value.selection_account_id = newValue.id
      } else {
        formData.value.selection_account_type = ''
        formData.value.selection_account_id = null
      }
    }

    // Watch for dialog opening
    watch(() => props.modelValue, async (isOpen) => {
      if (isOpen && accountOptions.value.length === 0) {
        await fetchFormData()
      }
    })

    const errorMessages = ref({})
    
    const clearErrors = () => {
      errorMessages.value = {}
      generalError.value = ''
    }

    // Add watchers for each form field to clear its error
    watch(() => formData.value.selection_account_type, () => {
      if (errorMessages.value.selection_account_type) {
        errorMessages.value.selection_account_type = null
      }
    })

    watch(() => formData.value.currency, () => {
      if (errorMessages.value.currency) {
        errorMessages.value.currency = null
      }
    })

    watch(() => formData.value.is_restricted, () => {
      if (errorMessages.value.is_restricted) {
        errorMessages.value.is_restricted = null
      }
    })

    const prepareFormData = () => {
      const effectiveCurrentDate = store.state.effectiveCurrentDate
      if (!effectiveCurrentDate) {
        throw new Error('Effective current date not set')
      }

      return {
        ...formData.value,
        effective_current_date: effectiveCurrentDate
      }
    }

    async function submitForm() {
      loading.value = true
      clearErrors()

      // Front-end validation
      const validationErrors = {}
      if (!formData.value.selection_account_type) {
        validationErrors.selection_account_type = ['Please select an account']
      }
      if (!formData.value.currency) {
        validationErrors.currency = ['Please select a currency']
      }
      if (!formData.value.is_restricted) {
        validationErrors.is_restricted = ['Please select a restriction option']
      }

      if (Object.keys(validationErrors).length > 0) {
        errorMessages.value = validationErrors
        loading.value = false
        return
      }

      try {
        const dataToSend = prepareFormData()
        console.log('[UpdateAccountPerformanceDialog] Submitting formData:', dataToSend)
        
        // First validate
        const validateResponse = await axiosInstance.post(
          '/database/api/update-account-performance/validate/',
          dataToSend
        )

        if (!validateResponse.data.valid) {
          throw new Error(validateResponse.data.message || 'Validation failed')
        }

        // If validation passed, emit update-started with the same prepared data
        emit('update-started', dataToSend)
        closeDialog()
        
      } catch (error) {
        console.error('Form submission error:', error)
        if (error.response?.data?.type === 'validation') {
          Object.keys(error.response.data.errors).forEach(field => {
            errorMessages.value[field] = error.response.data.errors[field]
          })
          errorMessages.value["selection_account_type"] = error.response.data.errors["selection_account_id"] ? "Wrong selection" : errorMessages.value["selection_account_type"]
        } else {
          generalError.value = error.response?.data?.message || 'An unexpected error occurred'
        }
      } finally {
        loading.value = false
      }
    }

    function closeDialog() {
      dialog.value = false
      formData.value = {
        selection_account_type: '',
        selection_account_id: null,
        currency: '',
        is_restricted: '',
        skip_existing_years: false
      }
      clearErrors()
      if (form.value) {
        form.value.resetValidation()
      }
    }

    watch(() => formData.value, () => {
      if (generalError.value) {
        generalError.value = ''
      }
    }, { deep: true })

    return {
      dialog,
      form,
      formData,
      loading,
      generalError,
      accountOptions,
      currencyOptions,
      restrictedOptions,
      selectedAccount,
      handleAccountChange,
      submitForm,
      closeDialog,
      errorMessages,
      prepareFormData,
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

