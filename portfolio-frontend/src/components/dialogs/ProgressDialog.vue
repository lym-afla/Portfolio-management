<template>
    <v-dialog v-model="dialogModel" persistent max-width="400px">
      <v-card>
        <v-card-title>{{ title }}</v-card-title>
        <v-card-text>
          <v-progress-linear
            :model-value="progress"
            height="25"
            color="primary"
          >
            <template v-slot:default="{ value }">
              <strong>{{ Math.ceil(value) }}%</strong>
            </template>
          </v-progress-linear>
          <v-alert v-if="error" type="error" class="mt-4">
            {{ error }}
          </v-alert>
        </v-card-text>
      </v-card>
    </v-dialog>
  </template>
  
  <script>
  import { computed, watch } from 'vue'
  
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
      error: {
        type: String,
        default: ''
      }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      const dialogModel = computed({
        get: () => props.modelValue,
        set: (value) => emit('update:modelValue', value)
      })

      watch(() => props.progress, (newValue) => {
        console.log('ProgressDialog: progress prop changed to', newValue)
      })

      return {
        dialogModel
      }
    }
  }
  </script>