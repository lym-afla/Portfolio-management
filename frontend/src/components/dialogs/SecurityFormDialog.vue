<template>
  <v-dialog v-model="dialog" max-width="800px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{
          isEdit ? 'Edit Security' : 'Add Security'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="
                (field.type === 'textinput' || field.type === 'url') &&
                shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :type="field.type === 'url' ? 'url' : 'text'"
              :hint="field.help_text"
              persistent-hint
            />
            <v-text-field
              v-else-if="
                field.type === 'dateinput' && shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              type="date"
              :hint="field.help_text"
              persistent-hint
            />
            <v-select
              v-else-if="field.type === 'select' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :hint="field.help_text"
              persistent-hint
            />
            <v-checkbox
              v-else-if="
                field.type === 'checkbox' && shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :label="field.label"
              :error-messages="errorMessages[field.name]"
              :hint="field.help_text"
              persistent-hint
            />
            <v-textarea
              v-else-if="
                field.type === 'textarea' && shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :hint="field.help_text"
              persistent-hint
            />
            <v-select
              v-else-if="
                field.type === 'selectmultiple' && shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              multiple
              chips
              :error-messages="errorMessages[field.name]"
              :hint="field.help_text"
              persistent-hint
            />
            <v-text-field
              v-else-if="
                field.type === 'numberinput' && shouldShowField(field.name)
              "
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              type="number"
              :hint="field.help_text"
              persistent-hint
            />
          </template>
        </v-form>
        <v-alert v-if="generalError" type="error" class="mt-3">
          {{ generalError }}
        </v-alert>
        <!-- Conflict sub-view: security already exists in the shared catalog -->
        <v-alert
          v-if="conflictData"
          type="warning"
          variant="tonal"
          class="mt-3"
          prominent
        >
          <p class="font-weight-bold mb-2">
            This security already exists in the catalog:
            {{ conflictData.existing_asset.name }}
            ({{ conflictData.existing_asset.ISIN }} /
            {{ conflictData.existing_asset.currency }})
          </p>

          <v-table
            v-if="Object.keys(conflictData.field_diff).length > 0"
            density="compact"
            class="mb-3"
          >
            <thead>
              <tr>
                <th>Field</th>
                <th>Catalog value</th>
                <th>Your submission</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(diff, field) in conflictData.field_diff"
                :key="field"
              >
                <td>{{ field }}</td>
                <td>{{ diff.existing }}</td>
                <td>{{ diff.submitted }}</td>
              </tr>
            </tbody>
          </v-table>

          <div v-if="conflictData.fillable.length > 0" class="mb-3">
            <p class="text-body-2 mb-1">
              Fields that will be added from your submission:
            </p>
            <v-chip
              v-for="field in conflictData.fillable"
              :key="field"
              size="small"
              class="mr-1 mb-1"
              color="success"
            >
              {{ field }}
            </v-chip>
          </div>

          <div class="d-flex gap-2 mt-2">
            <v-btn
              color="primary"
              variant="flat"
              @click="confirmConflict"
              :loading="isSubmitting"
            >
              Add to my portfolio
            </v-btn>
            <v-btn variant="text" @click="cancelConflict">Cancel</v-btn>
          </div>
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

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  createSecurity,
  updateSecurity,
  getSecurityFormStructure,
  isSecurityConflictPayload,
} from '@/services/api'
import type { SecurityConflictPayload } from '@/services/api'
import logger from '@/utils/logger'

const props = defineProps({
  modelValue: Boolean,
  editItem: Object,
  isImport: Boolean,
})
const emit = defineEmits([
  'update:modelValue',
  'security-added',
  'security-updated',
  'security-skipped',
])

const dialog = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const isEdit = computed(() => !!props.editItem)
// Form structure is served by an untyped backend endpoint; keep these
// loose-typed so vue-tsc doesn't choke on the existing JS-style access
// patterns. The new conflict payload below IS typed.
const form = ref<Record<string, any>>({})
const formFields = ref<any[]>([])
const errorMessages = ref<Record<string, any>>({})
const generalError = ref('')
const isSubmitting = ref(false)
const conflictData = ref<SecurityConflictPayload | null>(null)

const initializeForm = () => {
  form.value = formFields.value.reduce((acc, field) => {
    acc[field.name] = field.initial !== undefined ? field.initial : ''
    return acc
  }, {})
  errorMessages.value = formFields.value.reduce((acc, field) => {
    acc[field.name] = []
    return acc
  }, {})
}

const fetchFormStructure = async () => {
  try {
    const structure = await getSecurityFormStructure()
    formFields.value = structure.fields as any[]
    logger.log('Unknown', 'SecurityFormDialog formFields', formFields.value)
    initializeForm()
  } catch (error) {
    logger.error('Unknown', 'Error fetching form structure:', error)
    generalError.value = 'Failed to load form structure'
  }
}

const closeDialog = () => {
  // Only emit security-skipped if it's an import AND the dialog is closed via Cancel button
  if (props.isImport && !isSubmitting.value) {
    logger.log('Unknown', 'Emitting security-skipped from Cancel button') // Debug log
    emit('security-skipped')
  }
  dialog.value = false
  initializeForm()
  generalError.value = ''
  conflictData.value = null
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
    if (isEdit.value && !props.isImport) {
      response = await updateSecurity(props.editItem.id, form.value)
      emit('security-updated', response)
    } else {
      response = await createSecurity(form.value)
      logger.log('Unknown', 'createSecurity response:', response)
      if (props.isImport) {
        logger.log('Unknown', 'Emitting security-added with:', {
          id: response.id,
          name: response.name,
        })
        emit('security-added', { id: response.id, name: response.name })
      } else {
        emit('security-added', response)
      }
    }
    closeDialog()
  } catch (error) {
    logger.error('Unknown', 'Error submitting security:', error)

    // Check for a 409 conflict payload from resolve_or_create_asset.
    if (isSecurityConflictPayload(error)) {
      conflictData.value = error
      return  // Don't close the dialog — show the conflict sub-view.
    }

    // Existing per-field error handling (HTTP 400 from DRF).
    if (error.errors) {
      Object.keys(error.errors).forEach((key) => {
        if (key === '__all__') {
          generalError.value = error.errors[key][0]
        } else {
          errorMessages.value[key] = Array.isArray(error.errors[key])
            ? error.errors[key]
            : [error.errors[key]]
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

const confirmConflict = async () => {
  isSubmitting.value = true
  generalError.value = ''
  try {
    const response = await createSecurity({ ...form.value, confirm: true })
    emit('security-added', response)
    conflictData.value = null
    closeDialog()
  } catch (error) {
    logger.error('Unknown', 'Error confirming conflict:', error)
    generalError.value =
      error.message || 'Failed to add security. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}

const cancelConflict = () => {
  conflictData.value = null
}

const shouldShowField = (fieldName) => {
  if (fieldName === 'yahoo_symbol' && form.value.data_source !== 'YAHOO') {
    return false
  }
  if (fieldName === 'update_link' && form.value.data_source !== 'FT') {
    return false
  }
  if (
    fieldName === 'fund_fee' &&
    form.value.type !== 'Mutual fund' &&
    form.value.type !== 'ETF'
  ) {
    return false
  }
  if (fieldName === 'secid' && form.value.data_source !== 'MICEX') {
    return false
  }
  if (
    fieldName === 'tbank_instrument_uid' &&
    form.value.data_source !== 'TBANK'
  ) {
    return false
  }

  // Bond-specific fields
  const bondFields = [
    'initial_notional',
    'issue_date',
    'maturity_date',
    'coupon_rate',
    'coupon_frequency',
    'is_amortizing',
    'bond_type',
    'credit_rating',
  ]
  if (bondFields.includes(fieldName) && form.value.type !== 'Bond') {
    return false
  }

  return true
}

onMounted(fetchFormStructure)

watch(
  () => props.editItem,
  (newValue) => {
    if (newValue) {
      // Prefill the form with the editItem data
      form.value = { ...newValue }
    } else {
      initializeForm()
    }
    errorMessages.value = formFields.value.reduce((acc, field) => {
      acc[field.name] = []
      return acc
    }, {})
    generalError.value = ''
  },
  { immediate: true }
)
</script>
