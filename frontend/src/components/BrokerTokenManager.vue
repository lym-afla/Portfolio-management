<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      Broker API Tokens
      <v-spacer />
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        data-testid="add-broker-token"
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
import { computed, onMounted, ref, watch } from 'vue'
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
// Save completion and busy state belong to the form GENERATION that started
// them: cancelling and reopening bumps the generation, so a stale save can
// no longer close the new form or erase its draft, and the fresh form is
// not blocked by the older generation's busy flag.
const dialogGeneration = ref(0)
const savingGenerations = ref(new Map())

watch(showAddTokenDialog, (open) => {
  if (open) dialogGeneration.value += 1
})

const isSaving = computed(() => savingGenerations.value.get(dialogGeneration.value) === true)

// Delete busy is confirmation-OWNED (mirroring the composable): the Delete
// button for the CURRENTLY OPEN confirmation stays enabled while an older,
// replaced confirmation's delete is still in flight.
const deletingIdentity = ref(null)
const isDeleting = computed(() => {
  const candidate = deleteCandidate.value
  const identity = deletingIdentity.value
  if (!candidate || !identity) return false
  return identity.provider === candidate.key.provider && identity.tokenId === candidate.key.tokenId
})

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
  const candidate = deleteCandidate.value
  if (!candidate) return
  const identity = { provider: candidate.key.provider, tokenId: candidate.key.tokenId }
  // Only the SAME confirmation is blocked while its own delete is in
  // flight; a replacement confirmation may proceed immediately.
  if (
    deletingIdentity.value &&
    deletingIdentity.value.provider === identity.provider &&
    deletingIdentity.value.tokenId === identity.tokenId
  ) {
    return
  }
  deletingIdentity.value = identity
  try {
    await owner.confirmDelete()
  } finally {
    if (
      deletingIdentity.value &&
      deletingIdentity.value.provider === identity.provider &&
      deletingIdentity.value.tokenId === identity.tokenId
    ) {
      deletingIdentity.value = null
    }
  }
}

async function saveConnection(draft) {
  const generation = dialogGeneration.value
  if (savingGenerations.value.get(generation)) return
  const next = new Map(savingGenerations.value)
  next.set(generation, true)
  savingGenerations.value = next
  try {
    const outcome = await owner.saveConnection(draft)
    // A save whose form generation was closed and replaced is stale: it
    // must not close the newly reopened form (its draft is the new one's).
    if (generation !== dialogGeneration.value) return
    // Rejected saves keep the dialog (and entered values) for a retry;
    // every accepted close path lets the form erase the credential draft.
    if (outcome !== 'rejected') showAddTokenDialog.value = false
  } finally {
    const cleanup = new Map(savingGenerations.value)
    cleanup.delete(generation)
    savingGenerations.value = cleanup
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
