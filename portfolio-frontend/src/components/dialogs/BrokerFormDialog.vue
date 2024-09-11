<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ isEdit ? 'Edit Broker' : 'Add Broker' }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="field.type === 'textinput'"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-text-field>
            <v-select
              v-else-if="field.type === 'select'"
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-select>
            <v-checkbox
              v-else-if="field.type === 'checkbox'"
              v-model="form[field.name]"
              :label="field.label"
              :error-messages="errorMessages[field.name]"
            ></v-checkbox>
            <v-textarea
              v-else-if="field.type === 'textarea'"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-textarea>
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
import { createBroker, updateBroker, getBrokerFormStructure } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'BrokerFormDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
  },
  emits: ['update:modelValue', 'broker-added', 'broker-updated'],
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

    const { handleApiError } = useErrorHandler()

    const fetchFormStructure = async () => {
      try {
        const structure = await getBrokerFormStructure()
        if (structure && structure.fields) {
          formFields.value = structure.fields
          initializeForm()
        } else {
          throw new Error('Invalid form structure received')
        }
      } catch (error) {
        handleApiError(error)
      }
    }

    const initializeForm = () => {
      if (formFields.value && formFields.value.length > 0) {
        form.value = formFields.value.reduce((acc, field) => {
          if (field.type === 'checkbox') {
            acc[field.name] = false // Initialize checkboxes to false
          } else {
            acc[field.name] = ''
          }
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

    watch(() => props.editItem, (newValue) => {
      if (newValue) {
        form.value = { ...newValue }
      } else {
        initializeForm()
      }
      if (formFields.value && formFields.value.length > 0) {
        errorMessages.value = formFields.value.reduce((acc, field) => {
          acc[field.name] = []
          return acc
        }, {})
      }
      generalError.value = ''
    }, { immediate: true })

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

      // Prepare form data, ensuring boolean values for checkboxes
      const formData = Object.keys(form.value).reduce((acc, key) => {
        const field = formFields.value.find(f => f.name === key)
        if (field && field.type === 'checkbox') {
          acc[key] = Boolean(form.value[key]) // Ensure boolean value
        } else {
          acc[key] = form.value[key]
        }
        return acc
      }, {})

      try {
        let response
        if (isEdit.value) {
          response = await updateBroker(props.editItem.id, formData)
          emit('broker-updated', response)
        } else {
          response = await createBroker(formData)
          emit('broker-added', response)
        }
        closeDialog()
      } catch (error) {
        console.error('Error submitting broker:', error)
        if (error.response && error.response.status === 400 && error.response.data) {
          Object.keys(error.response.data).forEach(key => {
            if (Object.prototype.hasOwnProperty.call(errorMessages.value, key)) {
              errorMessages.value[key] = Array.isArray(error.response.data[key]) 
                ? error.response.data[key] 
                : [error.response.data[key]]
            } else {
              generalError.value = `${key}: ${error.response.data[key]}`
            }
          })
        } else {
          handleApiError(error)
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
  }
}
</script>
