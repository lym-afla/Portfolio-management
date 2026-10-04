<template>
  <v-dialog v-model="dialog" max-width="500px" aria-labelledby="fx-form-title">
    <v-card :id="focusCardId">
      <v-card-title id="fx-form-title">
        <span class="text-h5">{{
          isEdit ? 'Edit FX Rate' : 'Add FX Rate'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <section aria-label="FX rate">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">FX rate</h3>
          <p class="text-body-2 text-medium-emphasis mt-0 mb-2">
            The rate is quoted from the first currency to the second.
          </p>
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="field.type === 'datepicker'"
              v-model="form[field.name]"
              :label="field.label"
              type="date"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :disabled="isEdit && field.name === 'date'"
            />
            <v-text-field
              v-else-if="field.type === 'number'"
              v-model="form[field.name]"
              :label="field.label"
              type="number"
              step="0.0001"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            />
            <!--
              Currency code fields (from_currency/to_currency) come from
              form_structure as type:"text". Render them as text inputs, and
              lock them when the pair is preset (edit mode, or add-from-cell).
            -->
            <v-text-field
              v-else-if="field.type === 'text'"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :disabled="isEdit || presetPair"
              :maxlength="3"
            />
          </template>
          </section>
        </v-form>
        <v-alert v-if="generalError" type="error" class="mt-3" role="alert">
          {{ generalError }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-btn
          v-if="isEdit"
          color="error"
          variant="text"
          @click="$emit('fx-delete', editItem)"
          >Delete</v-btn
        >
        <v-spacer />
        <v-btn data-testid="dialog-cancel" :disabled="isSubmitting" @click="closeDialog">Cancel</v-btn>
        <v-btn
          data-testid="dialog-save"
          color="primary"
          variant="tonal"
          @click="submitForm"
          :loading="isSubmitting"
          >Save</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { addFXRate, updateFXRate, getFXFormStructure } from '@/services/api'
import { useDialogFormFocus } from '@/composables/useDialogFormFocus'
import logger from '@/utils/logger'

const props = defineProps({
  modelValue: Boolean,
  editItem: Object,
  // Optional prefilled values used when adding from an empty grid cell, e.g.
  // { date, from_currency, to_currency }. Distinct from `editItem` (which
  // switches the dialog to edit mode); `prefill` keeps Add mode but seeds the
  // form so the user only has to type the rate.
  prefill: {
    type: Object,
    default: null,
  },
})
const emit = defineEmits(['update:modelValue', 'fx-added', 'fx-updated', 'fx-delete'])

const dialog = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const { cardId: focusCardId } = useDialogFormFocus(dialog, 'fx-form')
const isEdit = computed(() => !!props.editItem)
// When a pair is preset (edit, or add-from-cell) the currency codes are fixed
// by the cell the user clicked — keep them read-only to avoid pair drift.
const presetPair = computed(
  () => isEdit.value || !!props.prefill?.from_currency
)
const form = ref({})
const formFields = ref([])
const errorMessages = ref({})
const generalError = ref('')
const isSubmitting = ref(false)

const initializeForm = () => {
  if (formFields.value && formFields.value.length > 0) {
    form.value = formFields.value.reduce((acc, field) => {
      acc[field.name] = ''
      return acc
    }, {})
    errorMessages.value = formFields.value.reduce((acc, field) => {
      acc[field.name] = []
      return acc
    }, {})
  } else {
    generalError.value = 'Failed to initialize form. Please try again.'
  }
}

const fetchFormStructure = async () => {
  try {
    const structure = await getFXFormStructure()
    if (structure && structure.fields) {
      formFields.value = structure.fields
      applyEditItem(props.editItem)
    } else {
      throw new Error('Invalid form structure received')
    }
  } catch (error) {
    logger.error('Unknown', 'Error fetching form structure:', error)
    generalError.value = 'Failed to load form structure. Please try again.'
  }
}

const closeDialog = () => {
  dialog.value = false
  initializeForm()
  generalError.value = ''
}

const submitForm = async () => {
  isSubmitting.value = true
  errorMessages.value = formFields.value.reduce((acc, field) => {
    acc[field.name] = []
    return acc
  }, {})
  generalError.value = ''

  try {
    let response
    if (isEdit.value) {
      response = await updateFXRate(form.value.id, form.value)
      emit('fx-updated', response)
    } else {
      response = await addFXRate(form.value)
      emit('fx-added', response)
    }
    closeDialog()
  } catch (error) {
    logger.error('Unknown', 'Error submitting FX rate:', error)
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
    form.value = { ...newValue }
    // Ensure the date is not editable when editing
    if (formFields.value) {
      const dateField = formFields.value.find(
        (field) => field.name === 'date'
      )
      if (dateField) {
        dateField.disabled = true
      }
    }
  } else {
    initializeForm()
    // Add-from-cell: seed the form with the prefilled date/pair so the user
    // only has to enter the rate. Date is also fixed (it's the cell's date).
    if (props.prefill) {
      form.value = { ...form.value, ...props.prefill }
      if (formFields.value) {
        const dateField = formFields.value.find(
          (field) => field.name === 'date'
        )
        if (dateField) {
          dateField.disabled = true
        }
      }
    } else if (formFields.value) {
      // Plain Add (from the toolbar): date is editable.
      const dateField = formFields.value.find(
        (field) => field.name === 'date'
      )
      if (dateField) {
        dateField.disabled = false
      }
    }
  }
  if (formFields.value && formFields.value.length > 0) {
    errorMessages.value = formFields.value.reduce((acc, field) => {
      acc[field.name] = []
      return acc
    }, {})
  }
  generalError.value = ''
}

watch(() => props.editItem, applyEditItem, { immediate: true })

// React to `prefill` changes too (e.g. the parent sets a prefill without
// changing editItem). Only applies in Add mode.
watch(
  () => props.prefill,
  (pf) => {
    if (props.editItem) return
    initializeForm()
    if (pf) {
      form.value = { ...form.value, ...pf }
      const dateField = formFields.value?.find((f) => f.name === 'date')
      if (dateField) dateField.disabled = true
    } else {
      const dateField = formFields.value?.find((f) => f.name === 'date')
      if (dateField) dateField.disabled = false
    }
  }
)
</script>
