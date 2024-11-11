<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>Update Account Performance</v-card-title>
      <v-card-text>
        <v-form ref="form">
          <v-select
            v-model="formData.account_or_group"
            :items="accountOptions"
            item-title="title"
            item-value="value"
            label="Accounts"
            :rules="[v => !!v || 'Account is required']"
            required
            class="mb-4"
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-if="item.raw.type === 'option'" v-bind="props" :title="null">
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
            :rules="[v => !!v || 'Currency is required']"
            required
            class="mb-4"
          />

          <v-select
            v-model="formData.is_restricted"
            :items="restrictedOptions"
            item-title="text"
            item-value="value"
            label="Restriction"
            :rules="[v => !!v || 'Restriction is required']"
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

export default {
  name: 'UpdateAccountPerformanceDialog',
  props: {
    modelValue: Boolean
  },
  emits: ['update:modelValue', 'update-started', 'update-error'],
  setup(props, { emit }) {
    const form = ref(null)
    const loading = ref(false)
    const generalError = ref('')
    const accountOptions = ref([])
    const currencyOptions = ref([])
    const restrictedOptions = ref([])

    const formData = ref({
      account_or_group: '',
      currency: '',
      is_restricted: '',
      skip_existing_years: false
    })

    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })

    const { handleApiError } = useErrorHandler()

    const store = useStore()

    const storeSelectedAccount = computed(() => {
      const selection = store.state.accountSelection
      return selection.type === 'all' ? 
          { type: 'all', id: null } : 
          { type: selection.type, id: selection.id }
    })
    const storeCurrency = computed(() => store.state.selectedCurrency)

    watch([storeSelectedAccount, accountOptions], ([newValue, options]) => {
      if (newValue && options.length > 0) {
        const matchingOption = options.find(
          option => option.type === 'option' && 
          option.value.type === newValue.type && 
          option.value.id === newValue.id
        )
        if (matchingOption) {
          formData.value.account_or_group = matchingOption.value
        }
      }
    }, { immediate: true })

    watch([storeCurrency, currencyOptions], ([newCurrency, options]) => {
      if (newCurrency && options.length > 0) {
        const selectedCurrency = options.find(option => option.text === newCurrency)
        if (selectedCurrency) {
          formData.value.currency = selectedCurrency.value
        }
      }
    }, { immediate: true })

    const formatAccountChoicesForAccountPerformance = (choices) => {
      if (!Array.isArray(choices)) {
        console.error('Received invalid choices format:', choices)
        return []
      }

      return formatAccountChoices(choices)
    }

    async function fetchFormData() {
      try {
        const data = await getAccountPerformanceFormData()
        accountOptions.value = formatAccountChoicesForAccountPerformance(data.account_choices)
        currencyOptions.value = Object.entries(data.currency_choices).map(([value, text]) => ({ value, text }))
        restrictedOptions.value = Object.entries(data.is_restricted_choices).map(([value, text]) => ({ value, text }))
      } catch (error) {
        handleApiError(error)
        emit('update-error', 'Failed to load form data')
      }
    }

    async function submitForm() {
      const { valid } = await form.value.validate()
      
      if (!valid) {
        return
      }

      loading.value = true
      generalError.value = ''

      try {
        emit('update-started', formData.value)
        closeDialog()
      } catch (error) {
        const errorData = JSON.parse(error.message)
        if (errorData.error) {
          generalError.value = errorData.error || 'Failed to start update'
        }
      } finally {
        loading.value = false
      }
    }

    function closeDialog() {
      dialog.value = false
      formData.value = {
        account_or_group: '',
        currency: '',
        is_restricted: '',
        skip_existing_years: false
      }
      if (form.value) {
        form.value.resetValidation()
      }
      generalError.value = ''
    }

    watch(() => dialog.value, async (isOpen) => {
      if (isOpen && accountOptions.value.length === 0) {
        await fetchFormData()
      }
    })

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
      submitForm,
      closeDialog
    }
  }
}
</script>

