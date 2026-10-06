<template>
  <div>
    <v-row>
      <v-col cols="12" md="6">
        <WorkspaceSection heading-id="security-basic" title="Basic Information">
          <div>
            <v-list>
              <v-list-item>
                <v-list-item-title>ISIN:</v-list-item-title>
                <v-list-item-subtitle>{{ view.identifier }}</v-list-item-subtitle>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Type:</v-list-item-title>
                <v-list-item-subtitle>{{ view.instrumentType }}</v-list-item-subtitle>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Currency:</v-list-item-title>
                <v-list-item-subtitle>{{ view.currency }}</v-list-item-subtitle>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>First Investment:</v-list-item-title>
                <v-list-item-subtitle>{{ view.firstInvestment ?? '' }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </div>
        </WorkspaceSection>
      </v-col>
      <v-col cols="12" md="6">
        <WorkspaceSection heading-id="security-performance" title="Performance Metrics">
          <div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="field in view.fields" :key="field.label">
                  <td>{{ field.label }}</td>
                  <td>
                    {{ field.value }}
                    <span v-if="field.explanation" class="text-caption text-grey">
                      {{ field.explanation }}</span
                    >
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </WorkspaceSection>
      </v-col>
    </v-row>

    <!-- Chart presentation stays with the entrypoint (D7: unchanged legacy
         ownership); these slots only fix the rendered position. -->
    <slot name="price-chart" />
    <slot name="position-chart" />
  </div>
</template>

<script setup lang="ts">
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import type { SecurityOverviewView } from './types'

defineProps<{
  view: SecurityOverviewView
}>()
</script>
