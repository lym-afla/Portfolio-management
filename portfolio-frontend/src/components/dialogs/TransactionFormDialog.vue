<template>
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{
          isEdit ? 'Edit Transaction' : 'Add Transaction'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="field.type === 'datepicker'"
              :model-value="form[field.name]"
              :label="field.label"
              type="date"
              :required="field.required"
              :error-messages="errors[field.name]"
              @update:model-value="(value) => setFieldValue(field.name, value)"
            />

            <v-autocomplete
              v-else-if="field.type === 'select'"
              :model-value="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              :error-messages="errors[field.name]"
              clearable
              @update:model-value="(value) => setFieldValue(field.name, value)"
            >
              <template v-slot:selection="{ item }">
                {{ item.raw ? item.raw.text : '' }}
              </template>
            </v-autocomplete>

            <v-text-field
              v-else-if="field.type === 'number'"
              :model-value="form[field.name]"
              :label="field.label"
              type="number"
              step="0.01"
              :required="field.required"
              :error-messages="errors[field.name]"
              @update:model-value="(value) => setFieldValue(field.name, value)"
            />

            <v-textarea
              v-else-if="field.type === 'textarea'"
              :model-value="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errors[field.name]"
              @update:model-value="(value) => setFieldValue(field.name, value)"
            />
          </template>
        </v-form>
        <v-alert v-if="generalError" type="error" class="mt-4">
          {{ generalError }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
        <v-btn
          color="blue darken-1"
          text
          @click="submitForm"
          :loading="isSubmitting"
          :disabled="!isFormValid"
        >
          Save
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { useForm } from 'vee-validate'
import * as yup from 'yup'
import {
  getTransactionFormStructure,
  addTransaction,
  updateTransaction,
} from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import logger from '@/utils/logger'

export default {
  name: 'TransactionFormDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
  },
  emits: ['update:modelValue', 'transaction-added', 'transaction-updated'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    })
    const isEdit = computed(() => !!props.editItem)
    const formFields = ref([])
    const generalError = ref('')
    const isSubmitting = ref(false)

    const { handleApiError } = useErrorHandler()

    const getNumberSchema = (field) => {
      let numberSchema = yup
        .number()
        .transform((value, originalValue) => {
          // Convert empty strings to null
          return originalValue === '' ? null : value
        })
        .nullable()

      // Apply specific validations based on the field name
      switch (field.name) {
        case 'cash_flow':
          numberSchema = numberSchema.test(
            'cash-flow-validation',
            'Cash flow must be negative for cash-out transactions and positive for cash-in transactions',
            function (value) {
              const type = this.parent.type
              if (value === null || value === undefined) return true
              if (type === 'Cash out') return value < 0
              if (type === 'Cash in') return value > 0
              return true
            }
          )
          break

        case 'price':
          numberSchema = numberSchema.positive('Price must be positive')
          break

        case 'quantity':
          numberSchema = numberSchema.test(
            'quantity-validation',
            'Quantity must be positive for buy transactions and negative for sell transactions',
            function (value) {
              const type = this.parent.type
              if (value === null || value === undefined) return true
              if (type === 'Buy') return value > 0
              if (type === 'Sell') return value < 0
              return true
            }
          )
          break

        case 'commission':
          numberSchema = numberSchema.negative('Commission must be negative')
          break

        default:
          break
      }

      return numberSchema
    }

    const schema = computed(() => {
      const schemaObj = {}
      formFields.value.forEach((field) => {
        if (field.type === 'number') {
          schemaObj[field.name] = getNumberSchema(field)
        } else {
          if (field.required) {
            schemaObj[field.name] = yup
              .mixed()
              .required(`${field.label} is required`)
          } else {
            schemaObj[field.name] = yup.mixed().nullable()
          }

          // Update security validation
          if (field.name === 'security') {
            schemaObj[field.name] = yup
              .mixed()
              .test(
                'security-validation',
                'Security must be selected for Buy, Sell, or Dividend transactions',
                function (value) {
                  const type = this.parent.type
                  // For Cash in/out transactions, security must be empty
                  if (type === 'Cash in' || type === 'Cash out') {
                    return value === null || value === undefined || value === ''
                  }
                  // For Buy, Sell, or Dividend transactions, security is required
                  if (['Buy', 'Sell', 'Dividend'].includes(type)) {
                    return value !== null && value !== undefined && value !== ''
                  }
                  // For other transaction types (if any), security is optional
                  return true
                }
              )
              .nullable()
          }
        }
      })
      return yup.object().shape(schemaObj)
    })

    const {
      handleSubmit,
      errors,
      resetForm,
      values: form,
      setValues,
      setFieldValue,
      setFieldError,
    } = useForm({
      validationSchema: schema,
      validateOnChange: true,
    })

    const clearFieldError = (fieldName) => {
      setFieldError(fieldName, '')
    }

    const isFormValid = computed(() => {
      return Object.keys(errors.value).length === 0
    })

    const fetchFormStructure = async () => {
      try {
        const response = await getTransactionFormStructure()
        formFields.value = response.fields
        initializeForm()
      } catch (error) {
        logger.error('Unknown', 'Error fetching form structure:', error)
        handleApiError(error)
      }
    }

    const initializeForm = () => {
      const initialValues = formFields.value.reduce((acc, field) => {
        acc[field.name] = field.type === 'number' ? null : ''
        return acc
      }, {})
      setValues(initialValues)
    }

    const submitForm = handleSubmit(async (values) => {
      const submittableValues = { ...values }

      isSubmitting.value = true
      generalError.value = ''

      try {
        let response
        if (isEdit.value) {
          response = await updateTransaction(
            submittableValues.id,
            submittableValues
          )
          emit('transaction-updated', response)
        } else {
          response = await addTransaction(submittableValues)
          emit('transaction-added', response)
        }
        closeDialog()
      } catch (error) {
        logger.error('Unknown', 'Error submitting transaction:', error)
        if (error && typeof error === 'object') {
          Object.entries(error).forEach(([key, value]) => {
            if (key === '__all__') {
              generalError.value = Array.isArray(value) ? value[0] : value
            } else {
              setFieldError(key, Array.isArray(value) ? value[0] : value)
            }
          })
        } else {
          generalError.value =
            error.message || 'An unexpected error occurred. Please try again.'
        }
      } finally {
        isSubmitting.value = false
      }
    })

    const closeDialog = () => {
      dialog.value = false
      resetForm()
      generalError.value = ''
    }

    const populateFormWithEditItem = () => {
      if (props.editItem && formFields.value.length > 0) {
        const formattedValues = { ...props.editItem }
        formFields.value.forEach((field) => {
          if (field.type === 'select' && formattedValues[field.name]) {
            if (typeof formattedValues[field.name] === 'object') {
              formattedValues[field.name] = String(
                formattedValues[field.name].id
              )
            } else {
              formattedValues[field.name] = String(formattedValues[field.name])
            }

            // Allow empty choice
            if (formattedValues[field.name] === '') {
              return
            }

            // Verify that the value exists in the choices
            const isValidChoice = field.choices.some(
              (choice) => choice.value === formattedValues[field.name]
            )
            if (!isValidChoice) {
              console.warn(
                `Invalid value for ${field.name}: ${formattedValues[field.name]}`
              )
              formattedValues[field.name] = '' // Set to empty string for empty choice
            }
          }
        })
        setValues(formattedValues)
      }
    }

    watch(
      () => props.editItem,
      (newValue) => {
        if (newValue) {
          populateFormWithEditItem()
        } else {
          initializeForm()
        }
      },
      { immediate: true }
    )

    onMounted(fetchFormStructure)

    return {
      dialog,
      isEdit,
      form,
      formFields,
      errors,
      generalError,
      isSubmitting,
      isFormValid,
      closeDialog,
      submitForm,
      clearFieldError,
      setFieldValue,
    }
  },
}
</script>
