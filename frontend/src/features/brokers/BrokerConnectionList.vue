<template>
  <div>
    <v-checkbox
      :model-value="showInactive"
      label="Show inactive tokens"
      hide-details
      class="mb-4"
      @update:model-value="emit('update:showInactive', Boolean($event))"
    />

    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <v-expansion-panels v-else>
      <v-expansion-panel
        v-for="panel in panels"
        :key="panel.provider"
      >
        <v-expansion-panel-title>
          <v-icon start>{{ panel.icon }}</v-icon>
          {{ panel.title }} ({{ rowsFor(panel.provider).length }})
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-list v-if="rowsFor(panel.provider).length">
            <template v-for="row in rowsFor(panel.provider)" :key="`${row.provider}-${row.tokenId}`">
              <v-list-item>
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="row.statusTone"
                        :icon="row.statusIcon"
                        class="mr-2"
                      />
                    </template>
                    {{ row.statusLabel }}
                  </v-tooltip>
                </template>

                <v-list-item-title>{{ row.label }}</v-list-item-title>

                <v-list-item-subtitle>
                  Created on {{ row.createdAtLabel }}
                  <v-chip
                    v-for="chip in row.chips"
                    :key="chip.text"
                    :color="chip.tone"
                    size="small"
                    class="ml-2"
                  >
                    {{ chip.text }}
                  </v-chip>
                </v-list-item-subtitle>

                <template v-slot:append>
                  <v-tooltip v-if="row.canTest" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-lock-check"
                        variant="text"
                        color="primary"
                        :loading="row.busy"
                        aria-label="Check token validity"
                        @click="emit('test', { provider: row.provider, tokenId: row.tokenId })"
                      />
                    </template>
                    Check token validity
                  </v-tooltip>

                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-key-remove"
                        variant="text"
                        color="error"
                        :loading="row.busy"
                        aria-label="Deactivate token"
                        @click="emit('revoke', { provider: row.provider, tokenId: row.tokenId })"
                      />
                    </template>
                    Deactivate token
                  </v-tooltip>

                  <v-tooltip v-if="row.canDelete" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        :loading="row.busy"
                        aria-label="Delete token permanently"
                        @click="emit('deleteRequest', { provider: row.provider, tokenId: row.tokenId })"
                      />
                    </template>
                    Delete token permanently
                  </v-tooltip>
                </template>
              </v-list-item>
              <v-alert
                v-if="rowErrors[`${row.provider}:${row.tokenId}`]"
                type="error"
                density="compact"
                variant="tonal"
                class="mt-2"
                role="alert"
              >
                {{ rowErrors[`${row.provider}:${row.tokenId}`] }}
              </v-alert>
            </template>
          </v-list>
          <v-alert v-else type="info" variant="tonal" class="mt-2">
            No tokens found
          </v-alert>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  BrokerConnectionDisplay,
  BrokerConnectionKey,
  BrokerProvider,
} from './types'

const props = defineProps<{
  connections: readonly BrokerConnectionDisplay[]
  loading: boolean
  showInactive: boolean
  rowErrors: Readonly<Record<string, string>>
}>()

const emit = defineEmits<{
  'update:showInactive': [value: boolean]
  test: [key: BrokerConnectionKey]
  revoke: [key: BrokerConnectionKey]
  deleteRequest: [key: BrokerConnectionKey]
}>()

const panels: ReadonlyArray<{ provider: BrokerProvider; title: string; icon: string }> = [
  { provider: 'tinkoff', title: 'Tinkoff tokens', icon: 'mdi-bank' },
  { provider: 'ib', title: 'Interactive Brokers tokens', icon: 'mdi-bank' },
  { provider: 'bybit', title: 'Bybit tokens', icon: 'mdi-bitcoin' },
  { provider: 'okx', title: 'OKX tokens', icon: 'mdi-bitcoin' },
]

const grouped = computed<Record<BrokerProvider, readonly BrokerConnectionDisplay[]>>(() => {
  const groups: Record<BrokerProvider, BrokerConnectionDisplay[]> = {
    tinkoff: [], ib: [], bybit: [], okx: [],
  }
  for (const row of props.connections) groups[row.provider].push(row)
  return groups
})

const rowsFor = (provider: BrokerProvider): readonly BrokerConnectionDisplay[] =>
  grouped.value[provider]
</script>
