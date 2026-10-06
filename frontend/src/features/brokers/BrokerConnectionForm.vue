<template>
  <v-dialog
    :model-value="open"
    max-width="500px"
    @update:model-value="emit('update:open', Boolean($event))"
  >
    <v-card :id="cardId">
      <v-card-title>Add New Token</v-card-title>
      <v-card-text>
        <v-form ref="formRef" v-model="isFormValid">
          <v-select
            v-model="selectedBrokerId"
            :items="brokerOptions"
            item-title="name"
            item-value="id"
            label="Select Broker"
            :rules="[(v: unknown) => !!v || 'Broker is required']"
            @update:model-value="handleBrokerSelection"
          />

          <v-text-field
            v-if="selectedProvider === 'tinkoff' || selectedProvider === 'ib'"
            v-model="draft.token"
            label="API Token"
            type="password"
            required
            :rules="[(v: string) => !!v || 'Token is required']"
          />

          <template v-if="selectedProvider === 'bybit' || selectedProvider === 'okx'">
            <v-text-field
              v-model="draft.apiKey"
              label="API Key"
              required
              :rules="[(v: string) => !!v || 'API key is required']"
            />
            <v-text-field
              v-model="draft.apiSecret"
              label="API Secret"
              type="password"
              required
              :rules="[(v: string) => !!v || 'API secret is required']"
            />
          </template>

          <template v-if="selectedProvider === 'bybit'">
            <v-switch
              v-model="draft.testnet"
              label="Bybit Testnet"
              color="warning"
              :true-value="true"
              :false-value="false"
              :true-icon="'mdi-check'"
              :false-icon="'mdi-close'"
              hide-details
            />
          </template>

          <template v-if="selectedProvider === 'okx'">
            <v-text-field
              v-model="draft.passphrase"
              label="Passphrase"
              type="password"
              required
              :rules="[(v: string) => !!v || 'Passphrase is required']"
            />
            <v-switch
              v-model="draft.simulatedTrading"
              label="OKX Simulated Trading"
              color="warning"
              :true-value="true"
              :false-value="false"
              :true-icon="'mdi-check'"
              :false-icon="'mdi-close'"
              hide-details
            />
          </template>

          <template v-if="selectedProvider === 'ib'">
            <v-text-field
              v-model="draft.accountId"
              label="Account ID"
              required
              :rules="[(v: string) => !!v || 'Account ID is required']"
            />
            <v-switch
              v-model="draft.paperTrading"
              label="Paper Trading"
              color="primary"
              :true-value="true"
              :false-value="false"
              :true-icon="'mdi-check'"
              :false-icon="'mdi-close'"
              hide-details
            />
          </template>

          <template v-if="selectedProvider === 'tinkoff'">
            <v-select
              v-model="draft.tokenType"
              :items="tokenTypeOptions"
              label="Token Type"
              disabled
              :rules="[
                (v: string) =>
                  v === 'read_only' ||
                  'Only read-only tokens are currently supported',
              ]"
            />

            <v-switch
              v-model="draft.sandboxMode"
              label="Sandbox Mode"
              color="warning"
              disabled
              :rules="[
                (v: boolean) =>
                  v === false || 'Sandbox mode is not currently supported',
              ]"
            />
          </template>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="primary"
          :loading="busy"
          :disabled="!isFormValid"
          @click="saveToken"
        >
          Save
        </v-btn>
        <v-btn color="error" @click="emit('update:open', false)">
          Cancel
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Broker Type Selection Dialog -->
  <v-dialog
    :model-value="brokerTypeDialogOpen"
    max-width="400"
    @update:model-value="brokerTypeDialogOpen = Boolean($event)"
  >
    <v-card>
      <v-card-title>Select Broker Type</v-card-title>
      <v-card-text>
        <p class="mb-4">
          Please specify the type of broker API for {{ unknownBrokerName }}
        </p>
        <v-radio-group v-model="selectedBrokerType" mandatory>
          <v-radio label="Tinkoff API" value="tinkoff" color="primary" />
          <v-radio
            label="Interactive Brokers API"
            value="ib"
            color="primary"
          />
          <v-radio label="Bybit API" value="bybit" color="primary" />
          <v-radio label="OKX API" value="okx" color="primary" />
        </v-radio-group>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="error" @click="cancelBrokerSelection">Cancel</v-btn>
        <v-btn color="primary" @click="confirmBrokerType">Confirm</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted, reactive } from 'vue'
import { useDialogFormFocus } from '@/composables/useDialogFormFocus'
import type {
  BrokerCredentialDraft,
  BrokerOption,
  BrokerProvider,
} from './types'

const props = defineProps<{
  open: boolean
  brokerOptions: ReadonlyArray<BrokerOption>
  busy: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  submit: [draft: BrokerCredentialDraft]
  error: [message: string]
}>()

const formRef = ref<{ validate: () => boolean | { valid: boolean }; reset: () => void } | null>(null)
const isFormValid = ref(false)

// The provider-specific credential draft lives ONLY here, for the open
// lifetime of the dialog. Success, cancellation, unmount and any other
// close path erase it; a rejected save keeps the dialog open with the
// entered values for a retry.
const draft = reactive({
  token: '',
  apiKey: '',
  apiSecret: '',
  passphrase: '',
  tokenType: 'read_only' as 'read_only' | 'full_access',
  sandboxMode: false,
  accountId: '',
  paperTrading: false,
  testnet: false,
  simulatedTrading: false,
})
const selectedProvider = ref<BrokerProvider | null>(null)
const selectedBrokerId = ref<number | null>(null)
const selectedBrokerType = ref<BrokerProvider | null>(null)
const unknownBrokerName = ref('')
const brokerTypeDialogOpen = ref(false)

const tokenTypeOptions = [
  { title: 'Read Only', value: 'read_only' },
  { title: 'Full Access', value: 'full_access' },
]

const { cardId } = useDialogFormFocus(
  computed(() => props.open),
  'broker-token-form',
)

function eraseDraft(): void {
  draft.token = ''
  draft.apiKey = ''
  draft.apiSecret = ''
  draft.passphrase = ''
  draft.tokenType = 'read_only'
  draft.sandboxMode = false
  draft.accountId = ''
  draft.paperTrading = false
  draft.testnet = false
  draft.simulatedTrading = false
  selectedProvider.value = null
  selectedBrokerId.value = null
  selectedBrokerType.value = null
  brokerTypeDialogOpen.value = false
}

watch(
  () => props.open,
  (open) => {
    if (!open) {
      formRef.value?.reset?.()
      eraseDraft()
    }
  },
)

onUnmounted(eraseDraft)

async function handleBrokerSelection(brokerId: number | null): Promise<void> {
  if (brokerId === null) return
  const broker = props.brokerOptions.find((option) => option.id === brokerId)
  if (!broker) return

  const brokerName = broker.name.toLowerCase()

  // Switching brokers clears every credential field and resets defaults.
  eraseDraft()
  selectedBrokerId.value = brokerId

  if (brokerName.includes('tinkoff')) {
    selectedProvider.value = 'tinkoff'
  } else if (brokerName.includes('interactive brokers')) {
    selectedProvider.value = 'ib'
  } else if (brokerName.includes('bybit')) {
    selectedProvider.value = 'bybit'
  } else if (brokerName.includes('okx')) {
    selectedProvider.value = 'okx'
  } else {
    unknownBrokerName.value = broker.name
    selectedProvider.value = null
    brokerTypeDialogOpen.value = true
  }
}

function cancelBrokerSelection(): void {
  selectedBrokerId.value = null
  selectedBrokerType.value = null
  brokerTypeDialogOpen.value = false
}

function confirmBrokerType(): void {
  if (!selectedBrokerType.value) {
    emit('error', 'Please select a broker type')
    return
  }
  selectedProvider.value = selectedBrokerType.value
  brokerTypeDialogOpen.value = false
  selectedBrokerType.value = null
}

// Vuetify 3's v-form validate() resolves to { valid: boolean, ... }; test
// stubs may return a plain boolean. Both shapes normalize here.
type ValidationResult = boolean | { valid: boolean } | void

const isValidationPass = (result: ValidationResult): boolean => {
  if (result === null || result === undefined) return true
  if (typeof result === 'boolean') return result
  if (typeof result === 'object' && 'valid' in result) {
    return result.valid === true
  }
  return true
}

async function saveToken(): Promise<void> {
  if (props.busy || !props.open) return
  if (!formRef.value) return
  // validate() is async in real Vuetify: AWAIT it — a truthiness check on
  // the promise would submit even when { valid: false } resolves.
  const validation = await Promise.resolve(formRef.value.validate() as ValidationResult)
  if (!isValidationPass(validation)) return
  // The await opens an ownership window: this dialog instance may have been
  // closed (or superseded) while validation ran — it must not submit then.
  if (!props.open || props.busy) return
  const brokerId = selectedBrokerId.value
  const provider = selectedProvider.value
  if (brokerId === null || provider === null) {
    emit('error', 'Please select a broker')
    return
  }
  let draftIntent: BrokerCredentialDraft
  if (provider === 'tinkoff') {
    draftIntent = {
      provider, brokerId, token: draft.token,
      tokenType: draft.tokenType, sandboxMode: draft.sandboxMode,
    }
  } else if (provider === 'ib') {
    draftIntent = {
      provider, brokerId, token: draft.token,
      accountId: draft.accountId, paperTrading: draft.paperTrading,
    }
  } else if (provider === 'bybit') {
    draftIntent = {
      provider, brokerId, apiKey: draft.apiKey,
      apiSecret: draft.apiSecret, testnet: draft.testnet,
    }
  } else {
    draftIntent = {
      provider, brokerId, apiKey: draft.apiKey,
      apiSecret: draft.apiSecret, passphrase: draft.passphrase,
      simulatedTrading: draft.simulatedTrading,
    }
  }
  emit('submit', draftIntent)
}

defineExpose({
  draft,
  selectedProvider,
  selectedBrokerType,
  handleBrokerSelection,
  confirmBrokerType,
  cancelBrokerSelection,
  saveToken,
  formRef,
})
</script>
