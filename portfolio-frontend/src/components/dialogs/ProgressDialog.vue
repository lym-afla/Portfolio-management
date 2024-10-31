<template>
  <v-dialog v-model="dialogModel" persistent max-width="600px">
    <v-card>
      <v-card-title class="d-flex align-center">
        {{ title }}
      </v-card-title>
      <v-card-text>
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
        <v-row no-gutters v-if="currentMessage" class="mb-4">
          <v-col cols="12">
            <v-card outlined class="mt-2 pa-2">
              <div class="d-flex align-center">
                <v-progress-circular
                  indeterminate
                  color="primary"
                  size="24"
                  width="2"
                  class="ml-2"
                ></v-progress-circular>
                <div class="text-body-2 ml-2">{{ currentMessage }}...</div>
              </div>
            </v-card>
          </v-col>
        </v-row>
        <v-row no-gutters class="mb-4">
          <v-col cols="12" class="text-center">
            <v-btn color="error" @click="stopImport" :disabled="!canStop">Stop Import</v-btn>
          </v-col>
        </v-row>
        <slot></slot>
        <!-- <v-alert v-for="(error, index) in errors" :key="index" type="error" class="mt-4"> -->
        <v-alert v-if="error" type="error" class="mt-4">
          {{ error }}
        </v-alert>
      </v-card-text>
      <v-card-actions v-if="error">
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="closeDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { computed, onBeforeUnmount, watch } from 'vue'

export default {
  name: 'ProgressDialog',
  props: {
    modelValue: Boolean,
    title: {
      type: String,
      default: 'Progress'
    },
    progress: {
      type: Number,
      default: 0
    },
    current: {
      type: Number,
      default: 0
    },
    total: {
      type: Number,
      default: 0
    },
    currentMessage: {
      type: String,
      default: ''
    },
    error: {
      type: String,
      default: ''
    },
    canStop: {
      type: Boolean,
      default: true
    },
    errors: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:modelValue', 'stop-import', 'reset'],
  setup(props, { emit }) {
    const dialogModel = computed({
      get: () => props.modelValue,
      set: (value) => {
        emit('update:modelValue', value)
        if (!value) {
          resetDialog()
        }
      }
    })

    const closeDialog = () => {
      dialogModel.value = false
    }

    const stopImport = () => {
      emit('stop-import')
    }

    const resetDialog = () => {
      emit('reset')
    }

    watch(() => props.progress, (newValue) => {
      console.log('ProgressDialog: progress prop changed to', newValue)
    })

    watch(() => props.current, (newValue) => {
      console.log('ProgressDialog: current prop changed to', newValue)
    })

    watch(() => props.total, (newValue) => {
      console.log('ProgressDialog: total prop changed to', newValue)
    })

    watch(() => props.currentMessage, (newValue) => {
      console.log('ProgressDialog: currentMessage prop changed to', newValue)
    })

    onBeforeUnmount(() => {
      resetDialog()
    })

    return {
      dialogModel,
      closeDialog,
      stopImport,
    }
  }
}
</script>