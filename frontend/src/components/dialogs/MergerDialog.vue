<template>
  <v-dialog v-model="dialog" max-width="600px">
    <template v-if="modelValue === undefined" v-slot:activator="{ props }">
      <v-btn color="primary" v-bind="props" prepend-icon="mdi-swap-horizontal" class="mr-2">
        Record Merger
      </v-btn>
    </template>
    <v-card :id="focusCardId">
      <v-card-title id="merger-form-title">
        <span class="text-h5">Record Merger</span>
      </v-card-title>
      <v-card-text>
        <v-form ref="formRef" @submit.prevent="submitForm">
          <section aria-label="Merger details">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Merger details</h3>
            <v-autocomplete
              v-model="form.oldSecurityId"
              :items="securities"
              item-title="name"
              item-value="id"
              label="Old Security *"
              clearable
            />

            <v-text-field
              v-model="form.mergerDate"
              label="Merger Date *"
              type="date"
            />
          </section>

          <section aria-label="Consideration" class="mt-4">
            <h3 class="text-subtitle-1 font-weight-medium mb-2">Consideration</h3>
            <v-autocomplete
              v-model="form.newSecurityId"
              :items="securities"
              item-title="name"
              item-value="id"
              label="New Security (leave empty for all-cash merger)"
              clearable
            />

            <v-text-field
              v-model="form.conversionRatio"
              label="Conversion Ratio (new shares per old share)"
              type="number"
              step="0.0001"
              hint="e.g. 0.75 means 1 old share becomes 0.75 new shares"
              persistent-hint
              :rules="[validateConversionRatio]"
            />

            <v-text-field
              v-model="form.cashPerShare"
              label="Cash Per Share (for all-cash or hybrid)"
              type="number"
              step="0.01"
            />

            <v-textarea
              v-model="form.notes"
              label="Notes (optional)"
              rows="2"
            />
          </section>
        </v-form>

        <v-alert v-if="error" type="error" class="mt-4">
          {{ error }}
        </v-alert>

        <!-- Preview -->
        <v-alert v-if="preview" type="info" class="mt-4" variant="tonal">
          <div><strong>Merger type:</strong> {{ preview.type }}</div>
          <div v-if="preview.newQuantity">
            <strong>New shares:</strong> {{ preview.newQuantity }} shares of {{ preview.newSecurityName }}
          </div>
          <div v-if="preview.cashTotal">
            <strong>Cash received:</strong> {{ preview.cashTotal }}
          </div>
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn data-testid="dialog-cancel" @click="closeDialog">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          @click="submitForm"
          :loading="isSubmitting"
          :disabled="!isFormValid"
        >
          Record Merger
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, reactive, shallowRef, computed, watch } from 'vue'
import { getSecurities } from '@/services/api'
import { createMerger } from '@/services/api'
import { useDialogFormFocus } from '@/composables/useDialogFormFocus'
import logger from '@/utils/logger'

const props = defineProps({ modelValue: { type: Boolean, default: undefined } })
const emit = defineEmits(['created', 'update:modelValue'])

const internalDialog = ref(false)
const dialog = computed({
  get: () => props.modelValue ?? internalDialog.value,
  set: value => {
    internalDialog.value = value
    emit('update:modelValue', value)
  },
})
const isSubmitting = ref(false)
const { cardId: focusCardId } = useDialogFormFocus(dialog, 'merger-form')
const error = ref(null)
const securities = shallowRef([])

const form = reactive({
  oldSecurityId: null,
  newSecurityId: null,
  mergerDate: new Date().toISOString().split('T')[0],
  conversionRatio: null,
  cashPerShare: null,
  notes: null,
})

const isAllCash = computed(() => !form.newSecurityId)
const isAllStock = computed(() => !!form.newSecurityId && !form.cashPerShare)

const mergerType = computed(() => {
  if (isAllCash.value) return 'All-cash'
  if (isAllStock.value) return 'All-stock'
  return 'Hybrid'
})

const preview = computed(() => {
  if (!form.oldSecurityId || !form.conversionRatio) return null
  const ratio = parseFloat(form.conversionRatio) || 0
  const cash = parseFloat(form.cashPerShare) || 0
  const newSec = securities.value.find((s) => s.id === form.newSecurityId)
  return {
    type: mergerType.value,
    newQuantity: form.newSecurityId ? `${ratio} per share` : null,
    newSecurityName: newSec ? newSec.name : 'N/A',
    cashTotal: cash > 0 ? `${cash} per share` : null,
  }
})

const isFormValid = computed(() => {
  if (!form.oldSecurityId || !form.mergerDate) return false
  if (form.newSecurityId && !form.conversionRatio) return false
  if (!form.newSecurityId && !form.cashPerShare) return false
  return true
})

const validateConversionRatio = () => {
  if (!form.newSecurityId) return true
  if (!form.conversionRatio) return 'Required when new security is selected'
  const val = parseFloat(form.conversionRatio)
  if (isNaN(val) || val <= 0) return 'Must be a positive number'
  return true
}

const fetchData = async () => {
  try {
    const secData = await getSecurities()
    const seen = new Set()
    securities.value = (secData || []).filter((s) => {
      if (seen.has(s.id)) return false
      seen.add(s.id)
      return true
    })
  } catch (err) {
    logger.error('MergerDialog', 'Error fetching securities:', err)
  }
}

const closeDialog = () => {
  dialog.value = false
  form.oldSecurityId = null
  form.newSecurityId = null
  form.mergerDate = new Date().toISOString().split('T')[0]
  form.conversionRatio = null
  form.cashPerShare = null
  form.notes = null
  error.value = null
}

const submitForm = async () => {
  error.value = null
  isSubmitting.value = true
  try {
    const result = await createMerger({
      oldSecurityId: form.oldSecurityId,
      newSecurityId: form.newSecurityId || undefined,
      mergerDate: form.mergerDate,
      conversionRatio: form.conversionRatio || undefined,
      cashPerShare: form.cashPerShare || undefined,
    })
    emit('created', result)
    closeDialog()
  } catch (err) {
    error.value =
      typeof err === 'string' ? err : err.error || 'Failed to record merger'
  } finally {
    isSubmitting.value = false
  }
}

watch(dialog, (val) => {
  if (val) fetchData()
}, { immediate: true })
</script>
