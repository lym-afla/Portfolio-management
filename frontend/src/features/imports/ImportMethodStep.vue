<template>
  <v-row>
    <!-- Direct Import Card -->
    <v-col cols="6">
      <v-tooltip
        :disabled="hasConnectedBrokers"
        text="Please add broker API tokens in User Settings to enable direct import"
        location="top"
        open-delay="200"
      >
        <template v-slot:activator="{ props }">
          <div v-bind="props">
            <v-card
              class="import-method-card"
              elevation="2"
              role="button"
              :tabindex="hasConnectedBrokers ? 0 : -1"
              :aria-disabled="!hasConnectedBrokers"
              :aria-label="'Direct Import'"
              @click="choose('api')"
              @keydown.enter.prevent="choose('api')"
              @keydown.space.prevent="choose('api')"
              :class="{
                selected: selected === 'api',
                disabled: !hasConnectedBrokers,
              }"
              :disabled="!hasConnectedBrokers"
            >
              <v-card-item>
                <v-avatar color="primary" size="64" class="mb-4">
                  <v-icon size="32" icon="mdi-api" />
                </v-avatar>
                <v-card-title>Direct Import</v-card-title>
                <v-card-subtitle class="text-wrap">
                  Import transactions directly from your broker
                  <v-chip size="x-small" color="primary" class="ml-2"
                    >Recommended</v-chip
                  >
                </v-card-subtitle>
                <v-card-text>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-check">
                      Faster and more reliable
                    </v-list-item>
                    <v-list-item prepend-icon="mdi-check">
                      No manual file preparation
                    </v-list-item>
                    <v-list-item prepend-icon="mdi-check">
                      Automatic broker detection
                    </v-list-item>
                  </v-list>
                </v-card-text>
              </v-card-item>
            </v-card>
          </div>
        </template>
      </v-tooltip>
    </v-col>

    <!-- File Import Card -->
    <v-col cols="6">
      <v-card
        class="import-method-card"
        elevation="2"
        role="button"
        tabindex="0"
        aria-label="File Import"
        @click="choose('file')"
        @keydown.enter.prevent="choose('file')"
        @keydown.space.prevent="choose('file')"
        :class="{ selected: selected === 'file' }"
      >
        <v-card-item>
          <v-avatar color="secondary" size="64" class="mb-4">
            <v-icon size="32" icon="mdi-file-upload" />
          </v-avatar>
          <v-card-title>File Import</v-card-title>
          <v-card-subtitle>
            Import from Excel or CSV file
          </v-card-subtitle>
          <v-card-text>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-check">
                Works with any broker
              </v-list-item>
              <v-list-item prepend-icon="mdi-check">
                Custom file formats
              </v-list-item>
              <v-list-item prepend-icon="mdi-check">
                Historical data import
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card-item>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import type { ImportMethod } from './types'

const props = defineProps<{
  selected: ImportMethod | null
  hasConnectedBrokers: boolean
}>()

const emit = defineEmits<{
  (event: 'select', method: ImportMethod): void
}>()

const choose = (method: ImportMethod) => {
  if (method === 'api' && !props.hasConnectedBrokers) return
  emit('select', method)
}
</script>

<style scoped>
.import-method-card {
  cursor: pointer;
  transition: all 0.3s;
  height: 100%;
  border: 2px solid transparent;
}

.import-method-card:not(.disabled):hover {
  transform: translateY(-4px);
}

.import-method-card.selected {
  border-color: rgb(var(--v-theme-primary));
}

.import-method-card.disabled {
  opacity: 0.7;
  cursor: not-allowed;
  pointer-events: auto;
}

.v-list-item {
  min-height: 32px;
}

.text-wrap {
  white-space: normal;
  word-wrap: break-word;
}
</style>
