<template>
  <v-dialog
    v-model="dialog"
    max-width="600px"
    aria-labelledby="transaction-form-title"
  >
    <v-card :id="formInstanceId">
      <v-card-title id="transaction-form-title">
        <span class="text-h5">{{
          isEdit ? 'Edit Transaction' : 'Add Transaction'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <!-- Visible section labels group the server-driven fields:
               identification vs. amounts. Sections with no visible field
               (conditional types) collapse entirely. -->
          <section v-if="detailFields.length">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Transaction details</h3>
            <FormFields
              :fields="detailFields"
              :value-for="(name) => form[name]"
              :error-for="(name) => errors[name]"
              :update="updateField"
            />
          </section>
          <section v-if="amountFields.length" class="mt-4">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Amounts</h3>
            <FormFields
              :fields="amountFields"
              :value-for="(name) => form[name]"
              :error-for="(name) => errors[name]"
              :update="updateField"
              :bond-price="isBondSelected"
            />
          </section>
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

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, getCurrentInstance } from 'vue'
import FormFields from './TransactionFormFields.vue'
import { useForm } from 'vee-validate'
import * as yup from 'yup'
import {
  getTransactionFormStructure,
  addTransaction,
  updateTransaction,
} from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import logger from '@/utils/logger'

const props = defineProps({
  modelValue: Boolean,
  editItem: Object,
})
const emit = defineEmits([
  'update:modelValue',
  'transaction-added',
  'transaction-updated',
])

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
        'Quantity must be positive for buy/corporate action and negative for sell transactions',
        function (value) {
          const type = this.parent.type
          if (value === null || value === undefined) return true
          if (type === 'Buy') return value > 0
          if (type === 'Sell') return value < 0
          // Stock split: positive for split (more shares), negative for reverse split
          if (type === 'Stock split') return value !== 0
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
            'Security must be selected for Buy, Sell, Dividend, or Stock split transactions',
            function (value) {
              const type = this.parent.type
              // For Cash in/out transactions, security must be empty
              if (type === 'Cash in' || type === 'Cash out') {
                return value === null || value === undefined || value === ''
              }
              // For Buy, Sell, Dividend, or Stock split transactions, security is required
              if (
                ['Buy', 'Sell', 'Dividend', 'Stock split'].includes(type)
              ) {
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

const isFormValid = computed(() => {
  return Object.keys(errors.value).length === 0
})

// Check if selected security is a bond
const isBondSelected = computed(() => {
  if (!form.security) return false
  const securityField = formFields.value.find((f) => f.name === 'security')
  if (!securityField || !securityField.choices) return false
  const selectedSecurity = securityField.choices.find(
    (choice) => choice.value === form.security
  )
  return selectedSecurity && selectedSecurity.type === 'Bond'
})

// Check if a field should be shown based on the current transaction type
const shouldShowField = (field) => {
  // If field has no show_for_types restriction, always show it
  if (!field.show_for_types || field.show_for_types.length === 0) {
    return true
  }
  // Otherwise, show only if current type is in the allowed types
  return field.show_for_types.includes(form.type)
}

// Field updates revalidate their field so a server-set error clears as
// soon as the user corrects the value (the same Yup schema decides; only
// the change-validation wiring was missing, which left rejected saves
// uncorrectable while the dialog stayed open).
const updateField = (name, value) => {
  setFieldValue(name, value, true)
}

// Visible section grouping: identification vs. amounts.
const AMOUNT_FIELD_NAMES = ['quantity', 'price', 'commission', 'cash_flow', 'split_from', 'split_to']
const isAmountField = (field) => AMOUNT_FIELD_NAMES.includes(field.name)
const detailFields = computed(() =>
  formFields.value.filter((field) => shouldShowField(field) && !isAmountField(field)))
const amountFields = computed(() =>
  formFields.value.filter((field) => shouldShowField(field) && isAmountField(field)))

// Initial focus goes to the first field; closing returns focus to the
// invoking control (the dialog component stays mounted after first open).
let previouslyFocused = null
// Fields can arrive after the open-time focus window (slow form structure):
// focus then, but only while this dialog instance is still the open one.
// The token cancels superseded loops (reopen, a later structure load) and
// the whole pending focus on unmount; the query is scoped to THIS dialog's
// overlay via its title id so a concurrently open sibling never receives
// the focus.
let focusToken = 0
// Permanent once the instance is gone: a structure response arriving after
// unmount must not START new focus work, and no poll may continue.
let focusDisposed = false
// Unique per component instance: the focus target is looked up inside THIS
// instance's own card element, so a replacement dialog of the same type
// (which shares the title id and DOM patterns) can never be matched.
const formInstanceId = `transaction-form-${getCurrentInstance()?.uid ?? 'unknown'}-card`
const focusFirstField = async () => {
  if (focusDisposed) return
  const token = ++focusToken
  await nextTick()
  for (let attempt = 0; attempt < 20; attempt++) {
    if (focusDisposed || token !== focusToken || !dialog.value) return
    const first = document.getElementById(formInstanceId)?.querySelector('input')
    if (first) {
      first.focus()
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
}

watch(dialog, async (open) => {
  if (open) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await focusFirstField()
  } else if (previouslyFocused?.isConnected) {
    previouslyFocused.focus()
    previouslyFocused = null
  }
}, { immediate: true })

// A dialog unmounted while its structure is still loading must never
// focus anything afterwards - not in this instance, whose late responses
// are now permanently disposed.
onUnmounted(() => {
  focusDisposed = true
  focusToken++
})

const initializeForm = () => {
  const initialValues = formFields.value.reduce((acc, field) => {
    acc[field.name] = field.type === 'number' ? null : ''
    return acc
  }, {})
  setValues(initialValues)
}

const fetchFormStructure = async () => {
  try {
    const response = await getTransactionFormStructure()
    formFields.value = response.fields
    // For new transactions, filter out "Merger in" and "Merger out"
    // from the type choices — they are technical/internal types
    if (!isEdit.value) {
      const typeField = formFields.value.find((f) => f.name === 'type')
      if (typeField && typeField.choices) {
        typeField.choices = typeField.choices.filter(
          (choice) =>
            choice.value !== 'Merger in' && choice.value !== 'Merger out'
        )
      }
    }
    if (props.editItem) populateFormWithEditItem()
    else initializeForm()
    // The fields (and with them the first focusable input) may only exist
    // now; a dialog closed in the meantime cancels via focusFirstField's
    // open check.
    if (dialog.value) focusFirstField()
  } catch (error) {
    logger.error('Unknown', 'Error fetching form structure:', error)
    handleApiError(error)
  }
}

const closeDialog = () => {
  dialog.value = false
  resetForm()
  generalError.value = ''
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

const populateFormWithEditItem = () => {
  if (props.editItem && formFields.value.length > 0) {
    const formattedValues = { ...props.editItem }
    formFields.value.forEach((field) => {
      if (field.type === 'datepicker' && formattedValues[field.name]) {
        formattedValues[field.name] = formattedValues[field.name].split('T')[0]
      }
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
</script>
