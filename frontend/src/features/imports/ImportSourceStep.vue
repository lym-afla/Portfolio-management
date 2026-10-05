<template>
  <div>
    <!-- API Import Form -->
    <v-expand-transition>
      <div v-if="method === 'api'">
        <v-select
          :model-value="selectedBroker"
          :items="brokers"
          item-title="name"
          :item-value="(item) => item"
          label="Select Broker Account"
          :error-messages="
            validation && !selectedBroker?.id
              ? 'Please select a broker account'
              : ''
          "
          required
          class="mb-4"
          @update:model-value="emit('update:selectedBroker', $event)"
          return-object
        />

        <v-row>
          <v-col cols="6">
            <v-text-field
              :model-value="dateRange?.from ?? null"
              label="From Date (Optional)"
              type="date"
              @update:model-value="
                emit('update:dateRange', {
                  from: $event,
                  to: dateRange?.to ?? null,
                })
              "
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              :model-value="dateRange?.to ?? null"
              label="To Date (Optional)"
              type="date"
              @update:model-value="
                emit('update:dateRange', {
                  from: dateRange?.from ?? null,
                  to: $event,
                })
              "
            />
          </v-col>
        </v-row>
      </div>
    </v-expand-transition>

    <!-- File Import Form -->
    <v-expand-transition>
      <div v-if="method === 'file'">
        <v-file-input
          :model-value="file"
          label="Select Excel or CSV file to import"
          accept=".csv, .xlsx, .xls"
          :rules="[(v) => !!v || 'File is required']"
          @change="emit('file-changed', $event)"
          :disabled="busy"
        />

        <v-checkbox
          :model-value="isGalaxy"
          label="Galaxy"
          class="mt-2"
          :disabled="busy"
          @update:model-value="emit('update:isGalaxy', $event)"
        />
      </div>
    </v-expand-transition>

    <!-- Common setting shown after method selection -->
    <v-expand-transition>
      <div v-if="method">
        <v-checkbox
          :model-value="confirmEveryTransaction"
          label="Confirm every transaction manually"
          class="mt-4"
          @update:model-value="emit('update:confirmEveryTransaction', $event)"
        />
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import type { ImportMethod } from './types'

defineProps<{
  method: ImportMethod | null
  brokers: Array<{ id: number; name: string }>
  selectedBroker: { id: number; name: string } | null
  dateRange: { from: string | null; to: string | null } | null
  file: File | null
  isGalaxy: boolean
  confirmEveryTransaction: boolean
  validation: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  (
    event: 'update:selectedBroker',
    value: { id: number; name: string } | null
  ): void
  (
    event: 'update:dateRange',
    value: { from: string | null; to: string | null }
  ): void
  (event: 'update:isGalaxy', value: boolean): void
  (event: 'update:confirmEveryTransaction', value: boolean): void
  (event: 'file-changed', payload: Event): void
}>()
</script>
