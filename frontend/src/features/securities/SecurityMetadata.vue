<template>
  <div>
    <v-row v-if="crypto">
      <v-col cols="12">
        <WorkspaceSection heading-id="security-crypto" title="Crypto Rewards">
          <div>
            <v-table density="compact">
              <tbody>
                <tr>
                  <td>Native rewards</td>
                  <td>{{ crypto.nativeQuantity }}</td>
                </tr>
                <tr>
                  <td>Fiat reward value</td>
                  <td>{{ crypto.fiatValue }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </WorkspaceSection>
      </v-col>
    </v-row>

    <v-row v-if="bond">
      <v-col cols="12">
        <WorkspaceSection heading-id="security-bond" title="Bond Information">
          <div>
            <v-row>
              <v-col cols="12" md="6">
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>Detail</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="field in bond.primary" :key="field.label">
                      <td>{{ field.label }}</td>
                      <td>
                        {{ field.value }}
                        <span
                          v-if="field.explanation"
                          class="text-caption text-grey"
                          >({{ field.explanation }})</span
                        >
                      </td>
                    </tr>
                  </tbody>
                </v-table>
              </v-col>
              <v-col cols="12" md="6">
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>Detail</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="field in bond.coupon" :key="field.label">
                      <td>{{ field.label }}</td>
                      <td>{{ field.value }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </v-col>
            </v-row>
          </div>
        </WorkspaceSection>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import type { BondMetadataView, CryptoRewardsView } from './types'

defineProps<{
  bond: BondMetadataView | null
  crypto: CryptoRewardsView | null
}>()
</script>
