<template>
  <v-dialog v-model="localDialog" max-width="600px" persistent>
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon start color="primary" class="mr-2">mdi-swap-horizontal</v-icon>
        Transfer Asset Between Accounts
      </v-card-title>

      <v-card-text>
        <v-form ref="form" v-model="valid">
          <v-row>
            <v-col cols="12">
              <v-autocomplete
                v-model="formData.security"
                :items="securities"
                :loading="loadingSecurities"
                item-title="text"
                item-value="value"
                label="Security *"
                :rules="[rules.required]"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-chart-line"
                @update:model-value="onSecurityChange"
              >
                <template v-slot:selection="{ item }">
                  {{ item.raw ? item.raw.text : '' }}
                </template>
              </v-autocomplete>
            </v-col>

            <v-col cols="12">
              <v-autocomplete
                v-model="formData.fromAccount"
                :items="fromAccounts"
                :loading="loadingAccounts"
                item-title="text"
                item-value="value"
                label="From Account *"
                :rules="[rules.required]"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-bank-minus"
                :disabled="!formData.security"
                @update:model-value="onFromAccountChange"
              >
                <template v-slot:selection="{ item }">
                  {{ item.raw ? item.raw.text : '' }}
                </template>
              </v-autocomplete>
            </v-col>

            <v-col cols="12">
              <v-autocomplete
                v-model="formData.toAccount"
                :items="toAccounts"
                :loading="loadingAccounts"
                item-title="text"
                item-value="value"
                label="To Account *"
                :rules="[rules.required, rules.differentAccount]"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-bank-plus"
              >
                <template v-slot:selection="{ item }">
                  {{ item.raw ? item.raw.text : '' }}
                </template>
              </v-autocomplete>
            </v-col>

            <v-col cols="12">
              <v-text-field
                :model-value="displayQuantity"
                label="Quantity to Transfer"
                :loading="loadingQuantity"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-counter"
                readonly
                hint="All holdings in the source account will be transferred"
                persistent-hint
              />
            </v-col>

            <v-col cols="12">
              <v-text-field
                v-model="formData.date"
                label="Transfer Date *"
                type="date"
                :rules="[rules.required]"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-calendar"
              />
            </v-col>

            <v-col cols="12">
              <v-alert type="info" variant="tonal" density="compact">
                <div class="text-caption">
                  This will create a sale from the source account and a purchase
                  in the destination account at the average cost basis (zero
                  realized gain).
                </div>
              </v-alert>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn color="grey" variant="text" @click="close">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="elevated"
          :loading="submitting"
          :disabled="!valid"
          @click="submit"
        >
          Transfer Asset
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, watch } from 'vue'
import {
  getTransactionFormStructure,
  transferAsset,
  getSecurityPosition,
} from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useStore } from 'vuex'
import logger from '@/utils/logger'

export default {
  name: 'AssetTransferDialog',
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['update:modelValue', 'transfer-completed'],
  setup(props, { emit }) {
    const { handleApiError } = useErrorHandler()
    const store = useStore()
    const form = ref(null)
    const valid = ref(false)
    const submitting = ref(false)
    const loadingSecurities = ref(false)
    const loadingAccounts = ref(false)
    const loadingQuantity = ref(false)
    const securities = ref([])
    const accounts = ref([])
    const currentQuantity = ref(null)

    const localDialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    })

    const formData = ref({
      security: null,
      fromAccount: null,
      toAccount: null,
      quantity: null,
      date: new Date().toISOString().split('T')[0],
    })

    const fromAccounts = computed(() => {
      // All accounts available
      return accounts.value
    })

    const toAccounts = computed(() => {
      // All accounts except the fromAccount
      return accounts.value.filter(
        (acc) => acc.value !== formData.value.fromAccount
      )
    })

    const displayQuantity = computed(() => {
      if (currentQuantity.value === null) {
        return ''
      }
      return currentQuantity.value.toString()
    })

    const rules = {
      required: (value) => !!value || 'Required',
      differentAccount: (value) =>
        value !== formData.value.fromAccount ||
        'Must be different from source account',
    }

    const fetchFormChoices = async () => {
      try {
        loadingSecurities.value = true
        loadingAccounts.value = true
        const response = await getTransactionFormStructure()

        // Extract security choices
        const securityField = response.fields.find(
          (field) => field.name === 'security'
        )
        if (securityField) {
          securities.value = securityField.choices
        }

        // Extract account choices
        const accountField = response.fields.find(
          (field) => field.name === 'account'
        )
        if (accountField) {
          accounts.value = accountField.choices
        }
      } catch (error) {
        handleApiError(error)
      } finally {
        loadingSecurities.value = false
        loadingAccounts.value = false
      }
    }

    const fetchCurrentPosition = async () => {
      if (!formData.value.security || !formData.value.fromAccount) {
        currentQuantity.value = null
        return
      }

      try {
        loadingQuantity.value = true
        const effectiveDate = store.state.effectiveCurrentDate || null

        const response = await getSecurityPosition(
          formData.value.security,
          formData.value.fromAccount,
          effectiveDate
        )

        currentQuantity.value = response.position || 0
        formData.value.quantity = currentQuantity.value

        logger.log(
          'AssetTransferDialog',
          `Current position for security ${formData.value.security} in account ${formData.value.fromAccount}: ${currentQuantity.value}`
        )
      } catch (error) {
        logger.error(
          'AssetTransferDialog',
          'Error fetching current position:',
          error
        )
        handleApiError(error)
        currentQuantity.value = 0
      } finally {
        loadingQuantity.value = false
      }
    }

    const onSecurityChange = () => {
      // Reset account selections and quantity when security changes
      formData.value.fromAccount = null
      formData.value.toAccount = null
      currentQuantity.value = null
      formData.value.quantity = null
    }

    const onFromAccountChange = () => {
      // Reset quantity when from account changes
      formData.value.toAccount = null
      fetchCurrentPosition()
    }

    const submit = async () => {
      if (!form.value.validate()) return

      if (!formData.value.quantity || formData.value.quantity <= 0) {
        handleApiError({
          error:
            'No holdings found in the source account for this security. Cannot transfer.',
        })
        return
      }

      try {
        submitting.value = true
        logger.log(
          'AssetTransferDialog',
          'Submitting transfer:',
          formData.value
        )

        await transferAsset(formData.value)

        logger.log('AssetTransferDialog', 'Transfer completed successfully')
        emit('transfer-completed')
        close()
      } catch (error) {
        handleApiError(error)
      } finally {
        submitting.value = false
      }
    }

    const close = () => {
      formData.value = {
        security: null,
        fromAccount: null,
        toAccount: null,
        quantity: null,
        date: new Date().toISOString().split('T')[0],
      }
      currentQuantity.value = null
      if (form.value) {
        form.value.reset()
      }
      localDialog.value = false
    }

    watch(
      () => props.modelValue,
      (newVal) => {
        if (newVal) {
          fetchFormChoices()
        }
      }
    )

    return {
      form,
      valid,
      submitting,
      loadingSecurities,
      loadingAccounts,
      loadingQuantity,
      securities,
      fromAccounts,
      toAccounts,
      formData,
      rules,
      localDialog,
      displayQuantity,
      onSecurityChange,
      onFromAccountChange,
      submit,
      close,
    }
  },
}
</script>
