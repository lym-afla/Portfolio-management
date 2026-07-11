<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ isEdit ? 'Edit Price' : 'Add Price' }}</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <v-select
            v-model="form.security"
            :items="securities"
            item-title="name"
            item-value="id"
            label="Security"
            required
            :error-messages="errorMessages.security"
          />
          <v-text-field
            v-model="form.date"
            label="Date"
            type="date"
            required
            :error-messages="errorMessages.date"
          />
          <v-text-field
            v-model="form.price"
            label="Price"
            type="number"
            step="0.01"
            required
            :error-messages="errorMessages.price"
          />
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
import { ref, computed, watch } from 'vue'
import { addPrice, updatePrice } from '@/services/api'
import logger from '@/utils/logger'

export default {
  name: 'PriceFormDialog',
  props: {
    modelValue: Boolean,
    editItem: Object,
    securities: Array,
  },
  emits: ['update:modelValue', 'price-added', 'price-updated'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    })
    const isEdit = computed(() => !!props.editItem)
    const form = ref({
      date: '',
      security: null,
      price: null,
    })
    const errorMessages = ref({
      date: [],
      security: [],
      price: [],
    })
    const generalError = ref('')
    const isSubmitting = ref(false)

    watch(
      () => props.editItem,
      (newValue) => {
        if (newValue) {
          form.value = { ...newValue }
        } else {
          form.value = { date: '', security: null, price: null }
        }
      },
      { immediate: true }
    )

    const closeDialog = () => {
      dialog.value = false
      form.value = { date: '', security: null, price: null }
      errorMessages.value = { date: [], security: [], price: [] }
      generalError.value = ''
    }

    const submitForm = async () => {
      isSubmitting.value = true
      errorMessages.value = { date: [], security: [], price: [] }
      generalError.value = ''

      try {
        let response
        if (isEdit.value) {
          response = await updatePrice(props.editItem.id, form.value)
          emit('price-updated', response)
        } else {
          response = await addPrice(form.value)
          emit('price-added', response)
        }
        closeDialog()
      } catch (error) {
        logger.error('Unknown', 'Error submitting price:', error)
        logger.log('Unknown', error.response, error.errors)
        if (error.errors) {
          const errors = error.errors
          if (errors) {
            Object.keys(errors).forEach((key) => {
              if (key === '__all__') {
                generalError.value = errors[key][0]
              } else {
                errorMessages.value[key] = Array.isArray(errors[key])
                  ? errors[key]
                  : [errors[key]]
              }
            })
          } else {
            generalError.value =
              'An unexpected error occurred. Please try again.'
          }
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
      errorMessages,
      generalError,
      isSubmitting,
      closeDialog,
      submitForm,
    }
  },
}
</script>
