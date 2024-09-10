<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ isEdit ? 'Edit FX Transaction' : 'Add FX Transaction' }}</span>
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
            ></v-text-field>
            <v-autocomplete
              v-else-if="field.type === 'select'"
              v-model="form[field.name]"
              :items="field.choices"
              item-title="text"
              item-value="value"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-autocomplete>
            <v-text-field
              v-else-if="field.type === 'number'"
              v-model="form[field.name]"
              :label="field.label"
              type="number"
              step="0.01"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
            ></v-text-field>
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
          class="mt-4"
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
import { getFXTransactionFormStructure, addFXTransaction, updateFXTransaction } from '@/services/api'

export default {
  name: 'FXTransactionDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
  },
  emits: ['update:modelValue', 'transaction-added', 'transaction-updated'],
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

    const initializeForm = () => {
      form.value = {}
      errorMessages.value = {}
      generalError.value = ''
    }

    const fetchFormStructure = async () => {
      try {
        const response = await getFXTransactionFormStructure()
        formFields.value = response.fields
        initializeForm()
      } catch (error) {
        console.error('Error fetching form structure:', error)
        generalError.value = 'Failed to load form structure. Please try again.'
      }
    }

    watch(() => props.editItem, (newValue) => {
      if (newValue) {
        form.value = { ...newValue }
      } else {
        initializeForm()
      }
    })

    // watch(() => props.modelValue, (newValue) => {
    //   if (newValue) {
    //     fetchFormStructure()
    //   }
    // })

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
        console.error('Error submitting FX transaction:', error)
        if (error && typeof error === 'object') {
          Object.entries(error).forEach(([key, value]) => {
            if (key === '__all__') {
              generalError.value = Array.isArray(value) ? value[0] : value
            } else {
              errorMessages.value[key] = Array.isArray(value) ? value : [value]
            }
          })
        } else {
          generalError.value = error.message || 'An unexpected error occurred. Please try again.'
        }
      } finally {
        isSubmitting.value = false
      }
    }

    onMounted(fetchFormStructure)

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