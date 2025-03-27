<template>
  <div v-if="showConfirmation" class="mt-4">
    <v-card outlined>
      <v-card-title class="text-h6 d-flex align-center">
        <v-icon
          start
          color="primary"
          icon="mdi-check-circle-outline"
          class="mr-2"
        />
        Confirm Transaction
      </v-card-title>
      <v-card-text>
        <v-row dense>
          <v-col cols="12" sm="6">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-calendar</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Date</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                formatDate(currentTransaction.date)
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col cols="12" sm="6">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-file-document-outline</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Type</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.type
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.security" cols="12">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-chart-line</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Security</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.security.name
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.quantity" cols="12" sm="4">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-numeric</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Quantity</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.quantity
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.price" cols="12" sm="4">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-currency-usd</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Price</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.price
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.total" cols="12" sm="4">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-cash</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Total</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.total
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.cash_flow" cols="12" sm="6">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-cash-multiple</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Cash Flow</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.cash_flow
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col v-if="currentTransaction.commission" cols="12" sm="6">
            <v-list-item>
              <template v-slot:prepend>
                <v-icon color="primary">mdi-percent</v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis"
                >Commission</v-list-item-title
              >
              <v-list-item-subtitle class="text-body-2">{{
                currentTransaction.commission
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
    <v-row class="mt-4">
      <v-col>
        <v-btn color="primary" block @click="$emit('confirm', null)">
          <v-icon start icon="mdi-check" />
          {{ securityMappingRequired ? 'Map and Confirm' : 'Confirm' }}
        </v-btn>
      </v-col>
      <v-col>
        <v-btn color="error" block @click="$emit('skip')">
          <v-icon start icon="mdi-close" />
          Skip
        </v-btn>
      </v-col>
    </v-row>
  </div>
</template>

<script>
import { format } from 'date-fns'

export default {
  name: 'TransactionConfirmationSection',
  props: {
    showConfirmation: {
      type: Boolean,
      default: false,
    },
    currentTransaction: {
      type: Object,
      default: () => ({}),
    },
    securityMappingRequired: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['confirm', 'skip'],
  methods: {
    formatDate(date) {
      return format(new Date(date), 'dd MMM yyyy')
    },
    // formatNumber(number) {
    //   return new Intl.NumberFormat().format(number);
    // },
    // formatCurrency(amount) {
    //   return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
    // }
  },
}
</script>
