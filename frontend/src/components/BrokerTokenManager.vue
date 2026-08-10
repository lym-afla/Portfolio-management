<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      Broker API Tokens
      <v-spacer />
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="showAddTokenDialog = true"
      >
        Add Token
      </v-btn>
    </v-card-title>

    <v-card-text>
      <v-checkbox
        v-model="showInactiveTokens"
        label="Show inactive tokens"
        hide-details
        class="mb-4"
      />

      <v-progress-linear v-if="loading" indeterminate color="primary" />

      <v-expansion-panels v-else>
        <!-- Tinkoff Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bank</v-icon>
            Tinkoff tokens ({{ filteredTinkoffTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredTinkoffTokens.length">
              <v-list-item
                v-for="token in filteredTinkoffTokens"
                :key="token.id"
              >
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="
                          token.is_active
                            ? 'mdi-check-circle'
                            : 'mdi-close-circle'
                        "
                        class="mr-2"
                      />
                    </template>
                    {{ token.is_active ? 'Valid token' : 'Invalid token' }}
                  </v-tooltip>
                </template>

                <v-list-item-title>
                  {{
                    token.token_type === 'read_only'
                      ? 'Read Only Token'
                      : 'Full Access Token'
                  }}
                </v-list-item-title>

                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>

                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-lock-check"
                        variant="text"
                        color="primary"
                        @click="testConnection('tinkoff', token.id)"
                        :loading="isTestingConnection[`tinkoff-${token.id}`]"
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
                        @click="revokeToken('tinkoff', token.id)"
                      />
                    </template>
                    Deactivate token
                  </v-tooltip>

                  <v-tooltip v-if="!token.is_active" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="confirmDeleteToken('tinkoff', token.id)"
                      />
                    </template>
                    Delete token permanently
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert v-else type="info" variant="tonal" class="mt-2">
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Interactive Brokers Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bank</v-icon>
            Interactive Brokers tokens ({{ filteredIBTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredIBTokens.length">
              <v-list-item v-for="token in filteredIBTokens" :key="token.id">
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="
                          token.is_active
                            ? 'mdi-check-circle'
                            : 'mdi-close-circle'
                        "
                        class="mr-2"
                      />
                    </template>
                    {{ token.is_active ? 'Valid token' : 'Invalid token' }}
                  </v-tooltip>
                </template>

                <v-list-item-title>
                  Account: {{ token.account_id }}
                </v-list-item-title>

                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="token.paper_trading"
                    color="warning"
                    size="small"
                    class="ml-2"
                  >
                    Paper Trading
                  </v-chip>
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>

                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-lock-check"
                        variant="text"
                        color="primary"
                        @click="testConnection('ib', token.id)"
                        :loading="isTestingConnection[`ib-${token.id}`]"
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
                        @click="revokeToken('ib', token.id)"
                      />
                    </template>
                    Deactivate token
                  </v-tooltip>

                  <v-tooltip v-if="!token.is_active" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="confirmDeleteToken('ib', token.id)"
                      />
                    </template>
                    Delete token permanently
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert v-else type="info" variant="tonal" class="mt-2">
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Bybit Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bitcoin</v-icon>
            Bybit tokens ({{ filteredBybitTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredBybitTokens.length">
              <v-list-item v-for="token in filteredBybitTokens" :key="token.id">
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="
                          token.is_active
                            ? 'mdi-check-circle'
                            : 'mdi-close-circle'
                        "
                        class="mr-2"
                      />
                    </template>
                    {{ token.is_active ? 'Stored token' : 'Inactive token' }}
                  </v-tooltip>
                </template>

                <v-list-item-title>
                  API key: {{ token.api_key }}
                </v-list-item-title>

                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="token.testnet"
                    color="warning"
                    size="small"
                    class="ml-2"
                  >
                    Testnet
                  </v-chip>
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>

                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-key-remove"
                        variant="text"
                        color="error"
                        @click="revokeToken('bybit', token.id)"
                      />
                    </template>
                    Deactivate token
                  </v-tooltip>

                  <v-tooltip v-if="!token.is_active" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="confirmDeleteToken('bybit', token.id)"
                      />
                    </template>
                    Delete token permanently
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert v-else type="info" variant="tonal" class="mt-2">
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- OKX Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bitcoin</v-icon>
            OKX tokens ({{ filteredOKXTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredOKXTokens.length">
              <v-list-item v-for="token in filteredOKXTokens" :key="token.id">
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="
                          token.is_active
                            ? 'mdi-check-circle'
                            : 'mdi-close-circle'
                        "
                        class="mr-2"
                      />
                    </template>
                    {{ token.is_active ? 'Stored token' : 'Inactive token' }}
                  </v-tooltip>
                </template>

                <v-list-item-title>
                  API key: {{ token.api_key }}
                </v-list-item-title>

                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="token.simulated_trading"
                    color="warning"
                    size="small"
                    class="ml-2"
                  >
                    Simulated Trading
                  </v-chip>
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>

                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-key-remove"
                        variant="text"
                        color="error"
                        @click="revokeToken('okx', token.id)"
                      />
                    </template>
                    Deactivate token
                  </v-tooltip>

                  <v-tooltip v-if="!token.is_active" location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="confirmDeleteToken('okx', token.id)"
                      />
                    </template>
                    Delete token permanently
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert v-else type="info" variant="tonal" class="mt-2">
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>

    <!-- Add Token Dialog -->
    <v-dialog v-model="showAddTokenDialog" max-width="500px">
      <v-card>
        <v-card-title>Add New Token</v-card-title>
        <v-card-text>
          <v-form ref="form" v-model="isFormValid">
            <v-select
              v-model="newToken.broker"
              :items="availableBrokers"
              item-title="name"
              item-value="id"
              label="Select Broker"
              :rules="[(v) => !!v || 'Broker is required']"
              @update:model-value="handleBrokerSelection"
            />

            <v-text-field
              v-if="selectedBrokerType === 'tinkoff' || selectedBrokerType === 'ib'"
              v-model="newToken.token"
              label="API Token"
              type="password"
              required
              :rules="[(v) => !!v || 'Token is required']"
            />

            <template v-if="selectedBrokerType === 'bybit' || selectedBrokerType === 'okx'">
              <v-text-field
                v-model="newToken.api_key"
                label="API Key"
                required
                :rules="[(v) => !!v || 'API key is required']"
              />
              <v-text-field
                v-model="newToken.api_secret"
                label="API Secret"
                type="password"
                required
                :rules="[(v) => !!v || 'API secret is required']"
              />
            </template>

            <template v-if="selectedBrokerType === 'bybit'">
              <v-switch
                v-model="newToken.testnet"
                label="Bybit Testnet"
                color="warning"
                :true-value="true"
                :false-value="false"
                :true-icon="'mdi-check'"
                :false-icon="'mdi-close'"
                hide-details
              />
            </template>

            <template v-if="selectedBrokerType === 'okx'">
              <v-text-field
                v-model="newToken.passphrase"
                label="Passphrase"
                type="password"
                required
                :rules="[(v) => !!v || 'Passphrase is required']"
              />
              <v-switch
                v-model="newToken.simulated_trading"
                label="OKX Simulated Trading"
                color="warning"
                :true-value="true"
                :false-value="false"
                :true-icon="'mdi-check'"
                :false-icon="'mdi-close'"
                hide-details
              />
            </template>

            <template v-if="selectedBrokerType === 'ib'">
              <v-text-field
                v-model="newToken.account_id"
                label="Account ID"
                required
                :rules="[(v) => !!v || 'Account ID is required']"
              />
              <v-switch
                v-model="newToken.paper_trading"
                label="Paper Trading"
                color="primary"
                :true-value="true"
                :false-value="false"
                :true-icon="'mdi-check'"
                :false-icon="'mdi-close'"
                hide-details
              />
            </template>

            <template v-if="selectedBrokerType === 'tinkoff'">
              <v-select
                v-model="newToken.token_type"
                :items="tokenTypeOptions"
                label="Token Type"
                disabled
                :rules="[
                  (v) =>
                    v === 'read_only' ||
                    'Only read-only tokens are currently supported',
                ]"
              />

              <v-switch
                v-model="newToken.sandbox_mode"
                label="Sandbox Mode"
                color="warning"
                disabled
                :rules="[
                  (v) =>
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
            @click="saveToken"
            :loading="isSaving"
            :disabled="!isFormValid"
          >
            Save
          </v-btn>
          <v-btn color="error" @click="showAddTokenDialog = false">
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add this dialog to your template -->
    <v-dialog v-model="showDeleteDialog" max-width="400">
      <v-card>
        <v-card-title>Delete Token</v-card-title>
        <v-card-text>
          Are you sure you want to permanently delete this token? This action
          cannot be undone.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            color="primary"
            variant="text"
            @click="showDeleteDialog = false"
            >Cancel</v-btn
          >
          <v-btn
            color="error"
            variant="text"
            @click="deleteToken"
            :loading="isDeleting"
          >
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Message Dialog -->
    <v-dialog v-model="showMessageDialog" max-width="400">
      <v-card>
        <v-card-title>{{ messageDialogTitle }}</v-card-title>
        <v-card-text>{{ messageDialogText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" @click="showMessageDialog = false">OK</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Broker Type Selection Dialog -->
    <v-dialog v-model="showBrokerTypeDialog" max-width="400">
      <v-card>
        <v-card-title>Select Broker Type</v-card-title>
        <v-card-text>
          <p class="mb-4">
            Please specify the type of broker API for {{ selectedBrokerName }}
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
  </v-card>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  getBrokerTokens,
  saveTinkoffToken,
  saveIBToken,
  saveBybitToken,
  saveOKXToken,
  testTinkoffConnection,
  testIBConnection,
  revokeToken as revokeTokenApi,
  deleteToken as deleteTokenApi,
  getAvailableBrokers,
} from '@/services/api'
import logger from '@/utils/logger'

const emit = defineEmits(['error', 'success', 'info'])

const form = ref(null)

const loading = ref(true)
const isFormValid = ref(false)
const showAddTokenDialog = ref(false)
const isSaving = ref(false)
const isTestingConnection = ref({})
const tinkoffTokens = ref([])
const ibTokens = ref([])
const bybitTokens = ref([])
const okxTokens = ref([])
const newToken = ref({
  broker: null,
  token: '',
  api_key: '',
  api_secret: '',
  passphrase: '',
  token_type: 'read_only',
  sandbox_mode: false,
  account_id: '',
  paper_trading: false,
  testnet: false,
  simulated_trading: false,
})
const brokerOptions = ref([
  { title: 'Tinkoff', value: 'tinkoff' },
  { title: 'Interactive Brokers', value: 'ib' },
  { title: 'Bybit', value: 'bybit' },
  { title: 'OKX', value: 'okx' },
])
const tokenTypeOptions = ref([
  { title: 'Read Only', value: 'read_only' },
  { title: 'Full Access', value: 'full_access' },
])
const showInactiveTokens = ref(false)
const showDeleteDialog = ref(false)
const isDeleting = ref(false)
const tokenToDelete = ref(null)
const brokerToDelete = ref(null)
const showMessageDialog = ref(false)
const messageDialogTitle = ref('')
const messageDialogText = ref('')
const availableBrokers = ref([])
const showBrokerTypeDialog = ref(false)
const selectedBrokerType = ref(null)
const selectedBrokerName = ref('')
const pendingBrokerId = ref(null)

const filteredTinkoffTokens = computed(() =>
  tinkoffTokens.value.filter((token) =>
    showInactiveTokens.value ? true : token.is_active
  )
)

const filteredIBTokens = computed(() =>
  ibTokens.value.filter((token) =>
    showInactiveTokens.value ? true : token.is_active
  )
)

const filteredBybitTokens = computed(() =>
  bybitTokens.value.filter((token) =>
    showInactiveTokens.value ? true : token.is_active
  )
)

const filteredOKXTokens = computed(() =>
  okxTokens.value.filter((token) =>
    showInactiveTokens.value ? true : token.is_active
  )
)

function handleError(error) {
  if (
    error.response?.status === 400 &&
    error.response.data?.message?.includes('already active')
  ) {
    messageDialogTitle.value = 'Token Already Exists'
    messageDialogText.value = error.response.data.message
    showMessageDialog.value = true
    showAddTokenDialog.value = false
    return
  }

  let errorMessage = 'An unexpected error occurred'

  if (error.response?.data?.error) {
    errorMessage = error.response.data.error
  } else if (error.response?.status === 403) {
    errorMessage = 'You do not have permission to perform this action'
  } else if (error.request) {
    errorMessage =
      'The server did not respond. Please check your internet connection'
  } else if (error.message) {
    errorMessage = error.message
  }

  emit('error', errorMessage)
}

async function fetchTokens() {
  logger.log('Unknown', 'Attempting to fetch tokens...')
  loading.value = true
  try {
    logger.log('Unknown', 'Making API call to getBrokerTokens...')
    const response = await getBrokerTokens()
    logger.log('Unknown', 'API response:', response)
    if (response) {
      tinkoffTokens.value = response.tinkoff_tokens || []
      ibTokens.value = response.ib_tokens || []
      bybitTokens.value = response.bybit_tokens || []
      okxTokens.value = response.okx_tokens || []
    }
  } catch (error) {
    logger.error('Unknown', 'Error in fetchTokens:', error)
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function testConnection(broker, tokenId) {
  const key = `${broker}-${tokenId}`
  isTestingConnection.value[key] = true
  try {
    if (broker === 'tinkoff') {
      const response = await testTinkoffConnection(tokenId)
      if (response?.data?.token) {
        const index = tinkoffTokens.value.findIndex((t) => t.id === tokenId)
        if (index !== -1) {
          tinkoffTokens.value[index] = response.data.token
        }
      }
      await fetchTokens()
      emit('success', 'Connection test successful')
    } else if (broker === 'ib') {
      await testIBConnection(tokenId)
      emit('success', 'Connection test successful')
    } else {
      emit('info', 'Connection testing is not implemented for this broker yet')
    }
  } catch (error) {
    handleError(error)
    await fetchTokens()
  } finally {
    isTestingConnection.value[key] = false
  }
}

async function revokeToken(broker, tokenId) {
  try {
    await revokeTokenApi(broker, tokenId)
    await fetchTokens()
    emit('success', 'Token revoked successfully')
  } catch (error) {
    handleError(error)
  }
}

async function saveToken() {
  if (!form.value.validate()) return

  isSaving.value = true
  try {
    const broker = availableBrokers.value.find(
      (b) => b.id === newToken.value.broker
    )
    if (!broker) throw new Error('Please select a broker')

    let response
    if (selectedBrokerType.value === 'tinkoff') {
      response = await saveTinkoffToken({
        broker: broker.id,
        token: newToken.value.token,
        token_type: newToken.value.token_type,
        sandbox_mode: newToken.value.sandbox_mode,
      })

      if (response.message?.includes('reactivated')) {
        messageDialogTitle.value = 'Token Reactivated'
        messageDialogText.value = response.message
        showMessageDialog.value = true
        showAddTokenDialog.value = false
        await fetchTokens()
        return
      }

      if (response.message) {
        emit('success', response.message)
      }

      if (response.id) {
        await testConnection('tinkoff', response.id)
      }

      showAddTokenDialog.value = false
      form.value.reset()
      resetNewToken()

      await fetchTokens()
    } else if (selectedBrokerType.value === 'ib') {
      await saveIBToken({
        broker: broker.id,
        token: newToken.value.token,
        account_id: newToken.value.account_id,
        paper_trading: newToken.value.paper_trading,
      })
      emit('success', 'Token saved successfully')
      showAddTokenDialog.value = false
      form.value.reset()
      resetNewToken()
      await fetchTokens()
    } else if (selectedBrokerType.value === 'bybit') {
      await saveBybitToken({
        broker: broker.id,
        api_key: newToken.value.api_key,
        api_secret: newToken.value.api_secret,
        testnet: newToken.value.testnet,
      })
      emit('success', 'Bybit token saved successfully')
      showAddTokenDialog.value = false
      form.value.reset()
      resetNewToken()
      await fetchTokens()
    } else if (selectedBrokerType.value === 'okx') {
      await saveOKXToken({
        broker: broker.id,
        api_key: newToken.value.api_key,
        api_secret: newToken.value.api_secret,
        passphrase: newToken.value.passphrase,
        simulated_trading: newToken.value.simulated_trading,
      })
      emit('success', 'OKX token saved successfully')
      showAddTokenDialog.value = false
      form.value.reset()
      resetNewToken()
      await fetchTokens()
    }
  } catch (error) {
    handleError(error)
  } finally {
    isSaving.value = false
  }
}

function formatDate(dateString) {
  if (!dateString) return 'N/A'
  try {
    const date = new Date(dateString)
    if (isNaN(date.getTime())) return 'Invalid Date'
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch (e) {
    logger.error('Unknown', 'Date formatting error:', e)
    return 'Invalid Date'
  }
}

function getTokenStatusText(token) {
  if (!token.is_active) return 'Inactive'
  return token.sandbox_mode ? 'Sandbox Mode' : 'Active'
}

function getTokenStatusColor(token) {
  if (!token.is_active) return 'error'
  return token.sandbox_mode ? 'warning' : 'success'
}

function watchBroker(newBroker) {
  if (newBroker === 'tinkoff') {
    newToken.value.token_type = 'read_only'
    newToken.value.sandbox_mode = false
  }
}

function resetNewToken() {
  newToken.value = {
    broker: null,
    token: '',
    api_key: '',
    api_secret: '',
    passphrase: '',
    token_type: 'read_only',
    sandbox_mode: false,
    account_id: '',
    paper_trading: false,
    testnet: false,
    simulated_trading: false,
  }
  selectedBrokerType.value = null
}

function confirmDeleteToken(broker, tokenId) {
  brokerToDelete.value = broker
  tokenToDelete.value = tokenId
  showDeleteDialog.value = true
}

async function deleteToken() {
  isDeleting.value = true
  try {
    await deleteTokenApi(brokerToDelete.value, tokenToDelete.value)
    await fetchTokens()
    emit('success', 'Token deleted successfully')
    showDeleteDialog.value = false
  } catch (error) {
    handleError(error)
  } finally {
    isDeleting.value = false
    brokerToDelete.value = null
    tokenToDelete.value = null
  }
}

async function loadBrokers() {
  try {
    const brokers = await getAvailableBrokers()
    availableBrokers.value = brokers
  } catch (error) {
    handleError(error)
  }
}

async function handleBrokerSelection(brokerId) {
  const broker = availableBrokers.value.find((b) => b.id === brokerId)
  if (!broker) return

  const brokerName = broker.name.toLowerCase()

  // Clear existing form settings
  newToken.value.token_type = 'read_only'
  newToken.value.sandbox_mode = false
  newToken.value.account_id = ''
  newToken.value.paper_trading = false
  newToken.value.api_key = ''
  newToken.value.api_secret = ''
  newToken.value.passphrase = ''
  newToken.value.testnet = false
  newToken.value.simulated_trading = false

  // Automatically determine type if name contains known broker
  if (brokerName.includes('tinkoff')) {
    selectedBrokerType.value = 'tinkoff'
    newToken.value.broker = brokerId
  } else if (brokerName.includes('interactive brokers')) {
    selectedBrokerType.value = 'ib'
    newToken.value.broker = brokerId
  } else if (brokerName.includes('bybit')) {
    selectedBrokerType.value = 'bybit'
    newToken.value.broker = brokerId
  } else if (brokerName.includes('okx')) {
    selectedBrokerType.value = 'okx'
    newToken.value.broker = brokerId
  } else {
    // Show dialog for user to specify broker type
    selectedBrokerName.value = broker.name
    pendingBrokerId.value = brokerId
    selectedBrokerType.value = null
    showBrokerTypeDialog.value = true
  }
}

function cancelBrokerSelection() {
  newToken.value.broker = null
  pendingBrokerId.value = null
  selectedBrokerType.value = null
  showBrokerTypeDialog.value = false
}

async function confirmBrokerType() {
  if (!selectedBrokerType.value) {
    emit('error', 'Please select a broker type')
    return
  }

  newToken.value.broker = pendingBrokerId.value
  // Set appropriate defaults based on broker type
  if (selectedBrokerType.value === 'tinkoff') {
    newToken.value.token_type = 'read_only'
    newToken.value.sandbox_mode = false
  } else if (selectedBrokerType.value === 'ib') {
    newToken.value.account_id = ''
    newToken.value.paper_trading = false
  } else if (selectedBrokerType.value === 'bybit') {
    newToken.value.testnet = false
  } else if (selectedBrokerType.value === 'okx') {
    newToken.value.simulated_trading = false
  }

  showBrokerTypeDialog.value = false
  pendingBrokerId.value = null
}

watch(
  () => newToken.value.broker,
  (newBroker) => {
    watchBroker(newBroker)
  }
)

logger.log('Unknown', 'BrokerTokenManager component created')

onMounted(async () => {
  logger.log('Unknown', 'BrokerTokenManager component mounted')
  await loadBrokers()
  await fetchTokens()
})
</script>
