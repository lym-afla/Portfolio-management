<template>
  <div>
    <v-select
      v-if="showCurrency"
      :model-value="currency"
      :items="currencies"
      label="Select Currency"
      class="mt-2"
      :rules="[(v) => !!v || 'Currency is required']"
      @update:model-value="emit('update:currency', $event)"
    />

    <template v-if="showAccount">
      <v-alert :type="identified ? 'success' : 'info'" class="mt-4 mb-4">
        {{
          identified
            ? `Broker account "${identifiedName}" was automatically identified. Please confirm or select a different broker account.`
            : 'Broker account could not be automatically identified. Please select a broker account below.'
        }}
      </v-alert>

      <v-select
        :model-value="selectedAccount"
        :items="accounts"
        item-title="title"
        item-value="id"
        label="Select Account"
        class="mt-2"
        :error-messages="
          validation && !selectedAccount ? 'Please select an account' : ''
        "
        required
        @update:model-value="emit('update:selectedAccount', $event)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    identified: boolean
    identifiedName: string | null
    accounts: Array<{ id: number; title: string }>
    selectedAccount: number | null
    validation: boolean
    showCurrency: boolean
    showAccount: boolean
    currency: string | null
    currencies: Array<{ title: string; value: string }>
  }>(),
  { showAccount: true }
)

const emit = defineEmits<{
  (event: 'update:selectedAccount', value: number | null): void
  (event: 'update:currency', value: string | null): void
}>()
</script>
