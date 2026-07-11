<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{
          isEdit ? 'Edit FX Rate' : 'Add FX Rate'
        }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
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
          </template>
        </v-form>
        <v-alert v-if="generalError" type="error" class="mt-3">
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

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { addFXRate, updateFXRate, getFXFormStructure } from '@/services/api'
import logger from '@/utils/logger'

export default {
  name: 'FXDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
  },
  emits: ['update:modelValue', 'fx-added', 'fx-updated'],
  setup(props, { emit }) {
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

    const fetchFormStructure = async () => {
      try {
        const structure = await getFXFormStructure()
        if (structure && structure.fields) {
          formFields.value = structure.fields
          initializeForm()
        } else {
          throw new Error('Invalid form structure received')
        }
      } catch (error) {
        logger.error('Unknown', 'Error fetching form structure:', error)
        generalError.value = 'Failed to load form structure. Please try again.'
      }
    }

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

    onMounted(fetchFormStructure)

    watch(
      () => props.editItem,
      (newValue) => {
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
          // Reset the date field to be editable when adding new FX rate
          if (formFields.value) {
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
      },
      { immediate: true }
    )

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

    return {
      dialog,
      isEdit,
      form,
      formFields,
      errorMessages,
      generalError,
      isSubmitting,
      closeDialog,
      submitForm,
    }
  },
}
</script>
