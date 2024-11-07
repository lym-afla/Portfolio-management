<template>
  <v-dialog v-model="dialog" max-width="800px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ isEdit ? 'Edit Security' : 'Add Security' }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="(field.type === 'textinput' || field.type === 'url') && shouldShowField(field.name)"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :type="field.type === 'url' ? 'url' : 'text'"
            ></v-text-field>
            <v-select
              v-else-if="field.type === 'select' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-select>
            <v-checkbox
              v-else-if="field.type === 'checkbox' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :label="field.label"
              :error-messages="errorMessages[field.name]"
            ></v-checkbox>
            <v-textarea
              v-else-if="field.type === 'textarea' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-textarea>
            <v-select
              v-else-if="field.type === 'selectmultiple' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              multiple
              chips
              :error-messages="errorMessages[field.name]"
            ></v-select>
            <v-text-field
              v-else-if="field.type === 'numberinput' && shouldShowField(field.name)"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-text-field>
          </template>
        </v-form>
        <v-alert
          v-if="generalError"
          type="error"
          class="mt-3"
        >
          {{ generalError }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
        <v-btn color="blue darken-1" text @click="submitForm" :loading="isSubmitting">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { createSecurity, updateSecurity, getSecurityFormStructure } from '@/services/api'

export default {
  name: 'SecurityFormDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
    isImport: Boolean,
  },
  emits: ['update:modelValue', 'security-added', 'security-updated', 'security-skipped'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })
    const isEdit = computed(() => !!props.editItem)
    const form = ref({})
    const formFields = ref([])
    const errorMessages = ref({})
    const generalError = ref('')
    const isSubmitting = ref(false)

    const fetchFormStructure = async () => {
      try {
        const structure = await getSecurityFormStructure()
        formFields.value = structure.fields
        console.log("SecurityFormDialog formFields", formFields.value)
        initializeForm()
      } catch (error) {
        console.error('Error fetching form structure:', error)
        generalError.value = 'Failed to load form structure'
      }
    }

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

    onMounted(fetchFormStructure)

    watch(() => props.editItem, (newValue) => {
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
    }, { immediate: true })

    const closeDialog = () => {
      // Only emit security-skipped if it's an import AND the dialog is closed via Cancel button
      if (props.isImport && !isSubmitting.value) {
        console.log('Emitting security-skipped from Cancel button')  // Debug log
        emit('security-skipped')
      }
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
        if (isEdit.value && !props.isImport) {
          response = await updateSecurity(props.editItem.id, form.value)
          emit('security-updated', response)
        } else {
          response = await createSecurity(form.value)
          if (props.isImport) {
            emit('security-added', { id: response.id, name: response.name })
          } else {
            emit('security-added', response)
          }
        }
        closeDialog()
      } catch (error) {
        console.error('Error submitting security:', error)
        if (error.errors) {
          Object.keys(error.errors).forEach(key => {
            if (key === '__all__') {
              generalError.value = error.errors[key][0]
            } else {
              errorMessages.value[key] = Array.isArray(error.errors[key]) ? error.errors[key] : [error.errors[key]]
            }
          })
        } else {
          generalError.value = error.message || 'An unexpected error occurred. Please try again.'
        }
      } finally {
        isSubmitting.value = false
      }
    }

    const shouldShowField = (fieldName) => {
      if (fieldName === 'yahoo_symbol' && form.value.data_source !== 'YAHOO') {
        return false
      }
      if (fieldName === 'update_link' && form.value.data_source !== 'FT') {
        return false
      }
      if (fieldName === 'fund_fee' && (form.value.type !== 'Mutual fund' && form.value.type !== 'ETF')) {
        return false
      }
      if (fieldName === 'secid' && form.value.data_source !== 'MICEX') {
        return false
      }
      return true
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
      shouldShowField,
    }
  }
}
</script>
