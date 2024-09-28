<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card v-if="dialog">
      <v-card-title>Update Broker Performance</v-card-title>
      <v-card-text>
        <v-form @submit.prevent="submitForm">
          <v-select
            v-model="formData.broker_or_group"
            :items="brokerOptions"
            item-title="title"
            item-value="value"
            label="Brokers"
            required
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-if="item.raw.type === 'option'" v-bind="props" :title="null">
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
            </template>
          </v-select>
          <v-select
            v-model="formData.currency"
            :items="currencyOptions"
            label="Currency"
            item-title="text"
            item-value="value"
            required
          ></v-select>
          <v-select
            v-model="formData.is_restricted"
            :items="restrictedOptions"
            label="Restriction"
            item-title="text"
            item-value="value"
            required
          ></v-select>
          <v-checkbox
            v-model="formData.skip_existing_years"
            label="Skip existing calculated years"
          ></v-checkbox>
          <v-btn type="submit" color="primary" :loading="loading" class="mr-4">Update</v-btn>
          <v-btn @click="closeDialog">Cancel</v-btn>
        </v-form>
      </v-card-text>
    </v-card>
  </v-dialog>

  <ProgressDialog
    v-model="showProgressDialog"
    :title="'Updating Broker Performance'"
    :progress="progress"
    :error="generalError"
  />
</template>

<script>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { updateBrokerPerformance, getBrokerPerformanceFormData } from '@/services/api'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'UpdateBrokerPerformanceDialog',
  components: {
    ProgressDialog
  },
  emits: ['update:modelValue', 'update-started', 'update-progress', 'update-completed', 'update-error'],
  props: {
    modelValue: Boolean,
  },
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })
    const loading = ref(false)
    const formData = reactive({
      broker_or_group: '',
      currency: '',
      is_restricted: '',
      skip_existing_years: false,
    })

    const brokerOptions = ref([])
    const currencyOptions = ref([])
    const restrictedOptions = ref([])

    const showProgressDialog = ref(false)
    const progress = ref(0)
    const generalError = ref('')
    const errors = ref([])

    const { handleApiError } = useErrorHandler()

    const fetchFormData = async () => {
      try {
        const data = await getBrokerPerformanceFormData()
        console.log('UpdateBrokerPerformanceDialog Response:', data)
        brokerOptions.value = formatBrokerChoicesForBrokerPerformance(data.broker_or_group_choices)
        currencyOptions.value = Object.entries(data.currency_choices).map(([value, text]) => ({ value, text }))
        restrictedOptions.value = Object.entries(data.is_restricted_choices).map(([value, text]) => ({ value, text }))
      } catch (error) {
        console.error('Error fetching form data:', error)
        generalError.value = 'Failed to load form data. Please try again.'
      }
    }

    const formatBrokerChoicesForBrokerPerformance = (choices) => {
      if (typeof choices !== 'object' || choices === null) {
        console.error('Received invalid choices format:', choices)
        return []
      }

      return Object.entries(choices).map(([key, value]) => {
        if (key.startsWith('__SEPARATOR_')) {
          return { type: 'divider' }
        } else {
          return {
            type: 'option',
            title: value,
            value: key
          }
        }
      })
    }

    const handleProgress = (event) => {
      const data = event.detail
      if (data.status === 'progress') {
        progress.value = data.progress
        emit('update-progress', data)
      } else if (data.status === 'complete') {
        showProgressDialog.value = false
        emit('update-completed')
      } else if (data.status === 'error') {
        errors.value.push(data.message)
        emit('update-error', data.message)
      }
    }

    onMounted(() => {
      window.addEventListener('brokerPerformanceUpdateProgress', handleProgress)
      fetchFormData()
    })

    onUnmounted(() => {
      window.removeEventListener('brokerPerformanceUpdateProgress', handleProgress)
    })

    const submitForm = async () => {
      dialog.value = false
      showProgressDialog.value = true
      progress.value = 0
      generalError.value = ''
      emit('update-started')

      try {
        await updateBrokerPerformance(formData)
      } catch (error) {
        handleApiError(error)
      } finally {
        if (!showProgressDialog.value) {
          loading.value = false
        }
      }
    }

    const closeDialog = () => {
      dialog.value = false
    }

    return {
      dialog,
      loading,
      formData,
      brokerOptions,
      currencyOptions,
      restrictedOptions,
      submitForm,
      closeDialog,
      showProgressDialog,
      progress,
      generalError,
      errors,
    }
  },
}
</script>
