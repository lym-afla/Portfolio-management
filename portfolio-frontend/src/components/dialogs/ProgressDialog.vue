<template>
  <v-dialog v-model="dialogModel" persistent max-width="600px">
    <v-card>
      <v-card-title class="d-flex align-center">
        {{ title }}
      </v-card-title>
      <v-card-text>
        <template v-if="total > 0">
          <v-progress-linear
            :model-value="progress"
            height="25"
            color="primary"
            class="mb-2"
          >
            <template v-slot:default="{ value }">
              <strong>{{ Math.ceil(value) }}%</strong>
            </template>
          </v-progress-linear>
          <v-row no-gutters>
            <v-col cols="12" class="text-center">
              <div class="text-subtitle-2 font-weight-medium">
                Processing {{ current }} of {{ total }}
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

<script>
import { computed, watch } from 'vue'
import logger from '@/utils/logger'

export default {
  name: 'ProgressDialog',
  props: {
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
  },
  emits: ['update:modelValue', 'stop-import', 'reset'],
  setup(props, { emit }) {
    const dialogModel = computed({
      get: () => props.modelValue,
      set: (value) => {
        emit('update:modelValue', value)
        if (!value) {
          emit('reset')
        }
      },
    })

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
          logger.log('Unknown', 'ProgressDialog: currentMessage changed to', newMessage)
        }
      }
    )

    return {
      dialogModel,
      closeDialog: () => {
        dialogModel.value = false
        emit('reset')
      },
      stopImport: () => emit('stop-import'),
    }
  },
}
</script>
