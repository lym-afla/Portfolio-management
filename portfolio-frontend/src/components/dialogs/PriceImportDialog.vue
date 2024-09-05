<template>
  <v-dialog v-model="dialog" max-width="800px">
    <v-card>
      <v-card-title>
        <span class="text-h5">Import Prices</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <template v-for="field in formFields" :key="field.name">
            <v-text-field
              v-if="field.type === 'textinput' || field.type === 'url'"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              :type="field.type === 'url' ? 'url' : 'text'"
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
            <v-select
              v-else-if="field.type === 'selectmultiple'"
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
              v-else-if="field.type === 'date'"
              v-model="form[field.name]"
              :label="field.label"
              :required="field.required"
              :error-messages="errorMessages[field.name]"
              type="date"
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
        <v-btn color="blue darken-1" text @click="submitForm" :loading="isSubmitting">Import</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { getPriceImportFormStructure, importPrices } from '@/services/api'

export default {
  name: 'PriceImportDialog',
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'prices-imported'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })
    const form = ref({})
    const formFields = ref([])
    const errorMessages = ref({})
    const generalError = ref('')
    const isSubmitting = ref(false)

    const fetchFormStructure = async () => {
      try {
        const structure = await getPriceImportFormStructure()
        formFields.value = structure.fields
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
        const response = await importPrices(form.value)
        emit('prices-imported', response)
        closeDialog()
      } catch (error) {
        console.error('Error importing prices:', error)
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

    return {
      dialog,
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
