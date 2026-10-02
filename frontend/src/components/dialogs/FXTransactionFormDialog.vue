<template>
  <v-dialog
    v-model="dialog"
    max-width="500px"
    aria-labelledby="fx-transaction-form-title"
  >
    <v-card>
      <v-card-title id="fx-transaction-form-title">
        <span class="text-h5">{{
          isEdit ? 'Edit FX Transaction' : 'Add FX Transaction'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <section v-if="detailFields.length">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Transaction details</h3>
            <FormFields :fields="detailFields" :value-for="(name) => form[name]" :error-for="(name) => errorMessages[name]" :update="setField" />
          </section>
          <section v-if="amountFields.length" class="mt-4">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Amounts</h3>
            <FormFields :fields="amountFields" :value-for="(name) => form[name]" :error-for="(name) => errorMessages[name]" :update="setField" />
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
          >Save</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import FormFields from './TransactionFormFields.vue'
import {
  getFXTransactionFormStructure,
  addFXTransaction,
  updateFXTransaction,
} from '@/services/api'
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
const form = ref({})
const formFields = ref([])
const errorMessages = ref({})
const generalError = ref('')
const isSubmitting = ref(false)

const initializeForm = () => {
  form.value = {}
  errorMessages.value = {}
  generalError.value = ''
}

// Visible section grouping and v-model plumbing for the shared renderer.
const AMOUNT_FIELD_NAMES = ['from_amount', 'to_amount', 'commission', 'rate', 'exchange_rate']
const isAmountField = (field) => AMOUNT_FIELD_NAMES.includes(field.name)
const detailFields = computed(() => formFields.value.filter((field) => !isAmountField(field)))
const amountFields = computed(() => formFields.value.filter((field) => isAmountField(field)))
const setField = (name, value) => {
  form.value = { ...form.value, [name]: value }
  // Editing a field clears its server-set error so a rejected save can be
  // corrected without reopening the dialog.
  if (errorMessages.value[name]) {
    const next = { ...errorMessages.value }
    delete next[name]
    errorMessages.value = next
  }
}

// Initial focus goes to the first field; closing returns focus to the
// invoking control.
let previouslyFocused = null
watch(dialog, async (open) => {
  if (open) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    // The teleported overlay becomes active asynchronously; wait briefly
    // for the first field rather than racing Vuetify's mount sequence.
    for (let attempt = 0; attempt < 20; attempt++) {
      const first = document.querySelector('.v-overlay--active[role="dialog"] input')
      if (first) {
        first.focus()
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 10))
    }
  } else if (previouslyFocused?.isConnected) {
    previouslyFocused.focus()
    previouslyFocused = null
  }
}, { immediate: true })

const fetchFormStructure = async () => {
  try {
    const response = await getFXTransactionFormStructure()
    formFields.value = response.fields
    applyEditItem(props.editItem)
  } catch (error) {
    logger.error('Unknown', 'Error fetching form structure:', error)
    generalError.value = 'Failed to load form structure. Please try again.'
  }
}

const closeDialog = () => {
  dialog.value = false
  initializeForm()
}

const submitForm = async () => {
  isSubmitting.value = true
  errorMessages.value = {}
  generalError.value = ''

  try {
    let response
    if (isEdit.value) {
      response = await updateFXTransaction(form.value.id, form.value)
      emit('transaction-updated', response)
    } else {
      response = await addFXTransaction(form.value)
      emit('transaction-added', response)
    }
    closeDialog()
  } catch (error) {
    logger.error('Unknown', 'Error submitting FX transaction:', error)
    if (error && typeof error === 'object') {
      Object.entries(error).forEach(([key, value]) => {
        if (key === '__all__') {
          generalError.value = Array.isArray(value) ? value[0] : value
        } else {
          errorMessages.value[key] = Array.isArray(value) ? value : [value]
        }
      })
    } else {
      generalError.value =
        error.message || 'An unexpected error occurred. Please try again.'
    }
  } finally {
    isSubmitting.value = false
  }
}

onMounted(fetchFormStructure)

function applyEditItem(newValue) {
  if (newValue) {
    logger.log('Unknown', 'newValue', newValue)
    form.value = { ...newValue }
    Object.keys(form.value).forEach((key) => {
      if (
        typeof form.value[key] === 'object' &&
        form.value[key] !== null
      ) {
        form.value[key] = String(form.value[key].id)
      }
    })
    if (form.value.date) {
      form.value.date = form.value.date.split('T')[0]
    }
    logger.log('Unknown', 'form', form.value)
  } else {
    initializeForm()
  }
}

watch(() => props.editItem, applyEditItem, { immediate: true })
</script>
