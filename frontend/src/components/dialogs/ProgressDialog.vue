<template>
  <v-dialog v-model="dialogModel" persistent max-width="600px">
    <v-card>
      <v-card-title class="d-flex align-center">
        {{ title }}
      </v-card-title>
      <v-card-text>
        <template v-if="total > 0">
          <!-- The percentage label sits OUTSIDE the moving fill in a stable,
               theme-contrasting element: a label rendered inside the bar's
               default slot is white-on-light over the unfilled track and
               unreadable at low percentages. -->
          <div
            class="d-flex align-center justify-space-between mb-1"
            data-testid="import-progress-label"
          >
            <span class="text-body-2 font-weight-medium">
              Processing {{ current }} of {{ total }}
            </span>
            <span class="text-body-2 font-weight-medium">
              {{ Math.ceil(progress) }}%
            </span>
          </div>
          <v-progress-linear
            :model-value="progress"
            height="12"
            color="primary"
            class="mb-2"
          />
          <v-row no-gutters>
            <v-col cols="12" class="text-center">
              <div class="text-subtitle-2 font-weight-medium">
                {{ Math.ceil(progress) }}% complete
              </div>
            </v-col>
          </v-row>
        </template>

        <v-row no-gutters v-if="currentMessage && !error" class="mb-4">
          <v-col cols="12">
            <v-card outlined class="mt-2 pa-2">
              <div class="d-flex align-center">
                <v-progress-circular
                  indeterminate
                  color="primary"
                  size="24"
                  width="2"
                  class="ml-2"
                />
                <div class="text-body-2 ml-2">{{ currentMessage }}</div>
              </div>
            </v-card>
          </v-col>
        </v-row>

        <v-alert
          v-if="error"
          type="error"
          class="mt-4"
          variant="tonal"
          closable
        >
          {{ error }}
        </v-alert>

        <v-row no-gutters class="mb-4" v-if="!error">
          <v-col cols="12" class="text-center">
            <v-btn color="error" @click="stopImport" :disabled="!canStop">
              Stop Import
            </v-btn>
          </v-col>
        </v-row>

        <slot />
      </v-card-text>

      <v-card-actions v-if="error">
        <v-spacer />
        <v-btn color="primary" @click="closeDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, watch } from 'vue'
import logger from '@/utils/logger'

const props = defineProps({
  modelValue: Boolean,
  title: {
    type: String,
    default: 'Progress',
  },
  progress: {
    type: Number,
    default: 0,
  },
  current: {
    type: Number,
    default: 0,
  },
  total: {
    type: Number,
    default: 0,
  },
  currentMessage: {
    type: String,
    default: '',
  },
  error: {
    type: String,
    default: '',
  },
  canStop: {
    type: Boolean,
    default: true,
  },
})
const emit = defineEmits(['update:modelValue', 'stop-import', 'reset'])

const dialogModel = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
    if (!value) {
      emit('reset')
    }
  },
})

const closeDialog = () => {
  dialogModel.value = false
  emit('reset')
}
const stopImport = () => emit('stop-import')

// Watch for error changes
watch(
  () => props.error,
  (newError) => {
    if (newError) {
      logger.log('Unknown', 'ProgressDialog error changed:', newError)
    }
  }
)

// Watch for message changes
watch(
  () => props.currentMessage,
  (newMessage) => {
    if (newMessage) {
      logger.log(
        'Unknown',
        'ProgressDialog: currentMessage changed to',
        newMessage
      )
    }
  }
)
</script>
