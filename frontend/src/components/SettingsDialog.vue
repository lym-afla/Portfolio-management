<template>
  <div>
    <v-btn
      v-if="!hideActivator"
      icon
      @click="openDialog"
      elevation="2"
      aria-label="Display preferences"
      :disabled="!context.canRead"
    >
      <v-icon>mdi-cog</v-icon>
    </v-btn>

    <v-dialog
      v-model="dialog"
      max-width="400px"
      persistent
      aria-labelledby="display-preferences-heading"
    >
      <v-card>
        <v-card-title id="display-preferences-heading" class="text-h5"
          >Display preferences</v-card-title
        >
        <v-card-text>
          <v-alert v-if="errors.general" type="error" role="alert">{{
            errors.general.join(' ')
          }}</v-alert>
          <v-form @submit.prevent="saveSettings" ref="form">
            <v-select
              v-if="!preferencesOnly"
              v-model="formData.default_currency"
              :items="currencyChoices"
              item-title="text"
              item-value="value"
              label="Currency"
              :error-messages="errors.default_currency"
              :disabled="isUpdating"
            />
            <v-text-field
              v-model="formData.digits"
              label="Number of digits"
              type="number"
              :error-messages="errors.digits"
              :disabled="isUpdating"
            />
            <v-text-field
              v-if="!preferencesOnly"
              v-model="formData.table_date"
              label="Date"
              type="date"
              :error-messages="errors.table_date"
              :disabled="isUpdating"
            />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            color="blue-darken-1"
            variant="text"
            @click="closeDialog"
            :disabled="isUpdating"
            >Close</v-btn
          >
          <v-btn
            color="blue-darken-1"
            variant="text"
            @click="saveSettings"
            :loading="isUpdating"
            :disabled="isUpdating"
          >
            Update
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'

const props = defineProps({
  hideActivator: Boolean,
  preferencesOnly: Boolean,
  requestChange: Function,
})
const context = usePortfolioContextStore()
const dialog = ref(false)
const form = ref(null)
const errors = ref({})
const saving = ref(false)
const isUpdating = computed(() => saving.value || context.isTransitioning)
const currencyChoices = computed(() => context.currencyChoices)
const formData = reactive({ default_currency: '', digits: 2, table_date: '' })
function openDialog() {
  if (!context.canRead) return
  const current = context.committed
  Object.assign(formData, {
    default_currency: current.currency,
    digits: current.digits,
    table_date: current.effectiveCurrentDate,
  })
  errors.value = {}
  dialog.value = true
}
function closeDialog() {
  dialog.value = false
  errors.value = {}
}
async function saveSettings() {
  if (isUpdating.value || !context.isReady) return
  errors.value = {}
  saving.value = true
  try {
    const intent = props.preferencesOnly
      ? { digits: Number(formData.digits) }
      : {
          effectiveCurrentDate: formData.table_date,
          currency: formData.default_currency,
          digits: Number(formData.digits),
        }
    if (props.requestChange) await props.requestChange(intent)
    else await context.changeContext(intent)
    closeDialog()
  } catch (error) {
    errors.value = {
      general: [error.message || 'Could not save portfolio settings'],
    }
  } finally {
    saving.value = false
  }
}
defineExpose({ openDialog })
</script>
