<template>
  <div>
    <v-row dense>
      <v-col cols="12">
        <v-card outlined>
          <v-list-item>
            <template v-slot:prepend>
              <v-avatar color="primary" size="40">
                <v-icon dark>mdi-database-import</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="text-h6">
              {{ result.totalTransactions }}
            </v-list-item-title>
            <v-list-item-subtitle
              >Total transactions processed</v-list-item-subtitle
            >
          </v-list-item>
        </v-card>
      </v-col>
      <v-col cols="6">
        <v-card outlined>
          <v-list-item>
            <template v-slot:prepend>
              <v-avatar color="success" size="40">
                <v-icon dark>mdi-check-circle</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="text-h6">
              {{ result.importedTransactions }}
            </v-list-item-title>
            <v-list-item-subtitle>Successfully imported</v-list-item-subtitle>
          </v-list-item>
        </v-card>
      </v-col>
      <v-col cols="6">
        <v-card outlined>
          <v-list-item>
            <template v-slot:prepend>
              <v-avatar color="warning" size="40">
                <v-icon dark>mdi-alert-circle</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="text-h6">
              {{ result.duplicateTransactions }}
            </v-list-item-title>
            <v-list-item-subtitle>Duplicates found</v-list-item-subtitle>
          </v-list-item>
        </v-card>
      </v-col>
      <v-col cols="6">
        <v-card outlined>
          <v-list-item>
            <template v-slot:prepend>
              <v-avatar color="error" size="40">
                <v-icon dark>mdi-alert-circle</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="text-h6">
              {{ result.skippedTransactions }}
            </v-list-item-title>
            <v-list-item-subtitle>Skipped transactions</v-list-item-subtitle>
          </v-list-item>
        </v-card>
      </v-col>
      <v-col cols="6">
        <v-card outlined>
          <v-list-item>
            <template v-slot:prepend>
              <v-avatar color="error" size="40">
                <v-icon dark>mdi-alert-circle</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="text-h6">
              {{ result.importErrors }}
            </v-list-item-title>
            <v-list-item-subtitle>Import Errors</v-list-item-subtitle>
          </v-list-item>
        </v-card>
      </v-col>
    </v-row>
    <v-alert
      v-if="result.warnings && result.warnings.length"
      type="warning"
      variant="tonal"
      closable
      class="mt-4"
      title="Some data sources could not be fetched"
    >
      <div class="text-body-2 mb-2">
        Import completed, but these endpoints returned errors and their data
        is not included in the results above:
      </div>
      <ul class="text-body-2 mb-0">
        <li v-for="(warning, index) in result.warnings" :key="index">
          <strong>{{ warning.endpoint }}</strong
          >: {{ warning.error }}
        </li>
      </ul>
    </v-alert>
  </div>
</template>

<script setup lang="ts">
import type { ImportResultData } from './types'

defineProps<{
  result: ImportResultData
}>()
</script>
