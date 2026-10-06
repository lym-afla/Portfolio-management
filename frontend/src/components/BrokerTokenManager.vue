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
      <BrokerConnectionList
        :connections="connections"
        :loading="loading"
        :show-inactive="showInactiveTokens"
        :row-errors="rowErrors"
        @update:show-inactive="showInactiveTokens = $event"
        @test="testConnection($event.provider, $event.tokenId)"
        @revoke="revokeToken($event.provider, $event.tokenId)"
        @delete-request="confirmDeleteToken($event.provider, $event.tokenId)"
      />
    </v-card-text>

    <BrokerConnectionForm
      v-model:open="showAddTokenDialog"
      :broker-options="brokerOptions"
      :busy="isSaving"
      @submit="saveConnection"
      @error="showError"
    />

    <!-- Delete connection confirmation: names the exact connection and never
         implies portfolio transactions are affected. -->
    <v-dialog :model-value="showDeleteDialog" max-width="400">
      <v-card>
        <v-card-title>Delete connection</v-card-title>
        <v-card-text>
          <p class="mb-2">
            Delete connection <strong>{{ deleteSubject }}</strong
            >? This permanently removes only the stored API credential. Your
            portfolio transactions are not affected.
          </p>
          <p>This action cannot be undone.</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="text" @click="cancelDelete">
            Cancel
          </v-btn>
          <v-btn color="error" variant="text" :loading="isDeleting" @click="deleteToken">
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Message Dialog -->
    <v-dialog :model-value="messageDialog !== null" max-width="400">
      <v-card>
        <v-card-title>{{ messageDialog?.title }}</v-card-title>
        <v-card-text>{{ messageDialog?.text }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" @click="dismissMessageDialog">OK</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
// D7 compatibility entrypoint: same component contract (emits error /
// success / info, "Broker API Tokens" surface), but list, form and request
// ownership now live in features/brokers. This file composes them and owns
// only the dialog wiring.
import { computed, onMounted, ref } from 'vue'
import BrokerConnectionList from '@/features/brokers/BrokerConnectionList.vue'
import BrokerConnectionForm from '@/features/brokers/BrokerConnectionForm.vue'
import { useBrokerConnections } from '@/features/brokers/useBrokerConnections'

const emit = defineEmits(['error', 'success', 'info'])

const owner = useBrokerConnections({
  emit: {
    error: (message) => emit('error', message),
    success: (message) => emit('success', message),
    info: (message) => emit('info', message),
  },
})

const {
  loading,
  connections,
  showInactive: showInactiveTokens,
  brokerOptions,
  messageDialog,
  deleteCandidate,
  refresh,
  loadBrokers,
  dismissMessageDialog,
  cancelDelete,
} = owner

const showAddTokenDialog = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)

const showDeleteDialog = computed(() => deleteCandidate.value !== null)
const deleteSubject = computed(() => deleteCandidate.value?.subject ?? '')

const rowErrors = computed(() => {
  const errors = {}
  for (const row of connections.value) {
    const message = owner.rowError({ provider: row.provider, tokenId: row.tokenId })
    if (message) errors[`${row.provider}:${row.tokenId}`] = message
  }
  return errors
})

const showError = (message) => emit('error', message)

function testConnection(provider, tokenId) {
  return owner.testConnection({ provider, tokenId })
}

function revokeToken(provider, tokenId) {
  return owner.revokeConnection({ provider, tokenId })
}

function confirmDeleteToken(provider, tokenId) {
  owner.requestDelete({ provider, tokenId })
}

async function deleteToken() {
  if (isDeleting.value) return
  isDeleting.value = true
  try {
    await owner.confirmDelete()
  } finally {
    isDeleting.value = false
  }
}

async function saveConnection(draft) {
  if (isSaving.value) return
  isSaving.value = true
  try {
    const outcome = await owner.saveConnection(draft)
    // Rejected saves keep the dialog (and entered values) for a retry;
    // every accepted close path lets the form erase the credential draft.
    if (outcome !== 'rejected') showAddTokenDialog.value = false
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  await loadBrokers()
  await refresh()
})

defineExpose({
  fetchTokens: refresh,
  testConnection,
  revokeToken,
  confirmDeleteToken,
  deleteToken,
  showInactiveTokens,
  showDeleteDialog,
  isSaving,
})
</script>
