// D7 broker connection owner: the single state/request boundary for the
// broker token surface. Owns the token lists, capability lookup, row
// commands (test/revoke/delete are distinct commands to distinct endpoints)
// and save orchestration around the existing API adapters. Requests are
// keyed by {provider, tokenId} with per-command ownership: a superseded or
// disposed request never emits, never refreshes, never mutates the lists
// and never releases another request's busy state. Display data crosses to
// components only as the allowlisted BrokerConnectionDisplay — credential
// records never leave this file, and nothing on these paths is logged.
import { computed, onScopeDispose, reactive, ref, shallowRef } from 'vue'

import {
  deleteToken as deleteTokenApi,
  getAvailableBrokers,
  getBrokerTokens,
  revokeToken as revokeTokenApi,
  saveBybitToken,
  saveIBToken,
  saveOKXToken,
  saveTinkoffToken,
  testIBConnection,
  testTinkoffConnection,
} from '@/services/api'
import {
  brokerKey,
  isBrokerProvider,
  type BrokerConnectionDisplay,
  type BrokerConnectionKey,
  type BrokerCredentialDraft,
  type BrokerMessageDialog,
  type BrokerOption,
  type BrokerOwnerEvents,
  type BrokerProvider,
  type BrokerSaveOutcome,
  type BrokerStatusChip,
} from './types'

interface TokenRecord {
  id: number
  is_active?: boolean
  created_at?: string | null
  token_type?: string
  account_id?: string
  paper_trading?: boolean
  api_key?: string
  testnet?: boolean
  simulated_trading?: boolean
}

interface TokensPayload {
  tinkoff_tokens?: TokenRecord[]
  ib_tokens?: TokenRecord[]
  bybit_tokens?: TokenRecord[]
  okx_tokens?: TokenRecord[]
}

interface BrokerOptionRecord {
  id: number
  name: string
}

const GENERIC_ERROR = 'An unexpected error occurred'
const UNSUPPORTED_TEST =
  'Connection testing is not implemented for this broker yet'

const supportsTesting = (provider: BrokerProvider): boolean =>
  provider === 'tinkoff' || provider === 'ib'

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null

// Incumbent error mapping (BrokerTokenManager.handleError), including its
// order: response body error text first, then permission/connectivity.
function mapBrokerError(cause: unknown): string {
  const record = asRecord(cause)
  const response = asRecord(record?.response)
  const data = asRecord(response?.data)
  if (typeof data?.error === 'string') return data.error
  if (response?.status === 403) {
    return 'You do not have permission to perform this action'
  }
  if (record?.request) {
    return 'The server did not respond. Please check your internet connection'
  }
  if (typeof record?.message === 'string') return record.message
  if (cause instanceof Error) return cause.message
  return GENERIC_ERROR
}

function isAlreadyActive(cause: unknown): string | null {
  const record = asRecord(cause)
  const response = asRecord(record?.response)
  const data = asRecord(response?.data)
  if (
    response?.status === 400 &&
    typeof data?.message === 'string' &&
    data.message.includes('already active')
  ) {
    return data.message
  }
  return null
}

function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return 'N/A'
  try {
    const date = new Date(dateString)
    if (Number.isNaN(date.getTime())) return 'Invalid Date'
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return 'Invalid Date'
  }
}

function toDisplay(
  provider: BrokerProvider,
  record: TokenRecord,
  busy: boolean,
): BrokerConnectionDisplay {
  const isActive = record.is_active === true
  const crypto = provider === 'bybit' || provider === 'okx'
  const chips: BrokerStatusChip[] = []
  if (provider === 'ib' && record.paper_trading) {
    chips.push({ text: 'Paper Trading', tone: 'warning' })
  }
  if (provider === 'bybit' && record.testnet) {
    chips.push({ text: 'Testnet', tone: 'warning' })
  }
  if (provider === 'okx' && record.simulated_trading) {
    chips.push({ text: 'Simulated Trading', tone: 'warning' })
  }
  if (!record.is_active) chips.push({ text: 'Inactive', tone: 'error' })
  let label: string
  if (provider === 'tinkoff') {
    label = record.token_type === 'read_only' ? 'Read Only Token' : 'Full Access Token'
  } else if (provider === 'ib') {
    label = `Account: ${record.account_id ?? ''}`
  } else {
    label = `API key: ${record.api_key ?? ''}`
  }
  return {
    provider,
    tokenId: record.id,
    label,
    statusIcon: isActive ? 'mdi-check-circle' : 'mdi-close-circle',
    statusLabel: crypto
      ? isActive ? 'Stored token' : 'Inactive token'
      : isActive ? 'Valid token' : 'Invalid token',
    statusTone: isActive ? 'success' : 'error',
    createdAtLabel: formatDate(record.created_at),
    chips,
    canTest: supportsTesting(provider),
    canRevoke: true,
    canDelete: !record.is_active,
    busy,
  }
}

export function useBrokerConnections(options: { emit: BrokerOwnerEvents }) {
  const { emit } = options

  const loading = ref(false)
  const lists = shallowRef<Map<BrokerProvider, TokenRecord[]>>(new Map())
  const showInactive = ref(false)
  const brokerOptions = ref<BrokerOption[]>([])
  const messageDialog = shallowRef<BrokerMessageDialog | null>(null)
  const deleteCandidate = shallowRef<{
    key: BrokerConnectionKey
    subject: string
  } | null>(null)
  const busyTokens = reactive(new Map<string, Set<number>>())
  const rowErrors = reactive(new Map<string, string>())
  let disposed = false
  let nextToken = 0
  const liveBySlot = new Map<string, number>()
  let listGeneration = 0
  let saveGeneration = 0
  let deleteBusy = false

  const stop = onScopeDispose(() => {
    disposed = true
  })

  // vue-tsc sees onScopeDispose's handler return; keep the unbind explicit.
  void stop

  const isBusy = (key: BrokerConnectionKey): boolean => {
    const tokens = busyTokens.get(brokerKey(key))
    return tokens !== undefined && tokens.size > 0
  }

  const rowError = (key: BrokerConnectionKey): string | null =>
    rowErrors.get(brokerKey(key)) ?? null

  const acquireBusy = (key: BrokerConnectionKey, token: number): void => {
    const slot = brokerKey(key)
    const tokens = busyTokens.get(slot) ?? new Set<number>()
    tokens.add(token)
    busyTokens.set(slot, tokens)
  }

  const releaseBusy = (key: BrokerConnectionKey, token: number): void => {
    const slot = brokerKey(key)
    const tokens = busyTokens.get(slot)
    if (!tokens) return
    tokens.delete(token)
    if (tokens.size === 0) busyTokens.delete(slot)
  }

  // A command owns its row slot until a NEWER command of the same kind on
  // the same row supersedes it or the owner is disposed; stale completions
  // stay silent end to end.
  const claimSlot = (slot: string): number => {
    const token = ++nextToken
    liveBySlot.set(slot, token)
    return token
  }
  const ownsSlot = (slot: string, token: number): boolean =>
    !disposed && liveBySlot.get(slot) === token

  const handleError = (key: BrokerConnectionKey | null, cause: unknown): void => {
    const message = mapBrokerError(cause)
    if (key) rowErrors.set(brokerKey(key), message)
    emit.error(message)
  }

  const assignLists = (payload: TokensPayload): void => {
    const next = new Map<BrokerProvider, TokenRecord[]>()
    next.set('tinkoff', payload.tinkoff_tokens ?? [])
    next.set('ib', payload.ib_tokens ?? [])
    next.set('bybit', payload.bybit_tokens ?? [])
    next.set('okx', payload.okx_tokens ?? [])
    lists.value = next
  }

  async function refresh(): Promise<void> {
    if (disposed) return
    const generation = ++listGeneration
    loading.value = true
    try {
      const payload = (await getBrokerTokens()) as TokensPayload
      if (disposed || generation !== listGeneration) return
      assignLists(payload)
    } catch (cause) {
      if (disposed || generation !== listGeneration) return
      handleError(null, cause)
    } finally {
      if (!disposed && generation === listGeneration) loading.value = false
    }
  }

  async function loadBrokers(): Promise<void> {
    try {
      const brokers = (await getAvailableBrokers()) as BrokerOptionRecord[]
      if (!disposed) {
        brokerOptions.value = brokers.map((broker) => ({
          id: broker.id,
          name: broker.name,
        }))
      }
    } catch (cause) {
      if (!disposed) handleError(null, cause)
    }
  }

  async function testConnection(key: BrokerConnectionKey): Promise<{ status: 'accepted' | 'discarded' }> {
    const slot = `${brokerKey(key)}:test`
    if (!supportsTesting(key.provider)) {
      emit.info(UNSUPPORTED_TEST)
      return { status: 'accepted' }
    }
    if (disposed) return { status: 'discarded' }
    const token = claimSlot(slot)
    acquireBusy(key, token)
    rowErrors.delete(brokerKey(key))
    try {
      if (key.provider === 'tinkoff') {
        await testTinkoffConnection(key.tokenId)
      } else {
        // Incumbent parity: only the Tinkoff branch refreshes after a
        // successful test; all failure paths refresh.
        await testIBConnection(key.tokenId)
        if (!ownsSlot(slot, token)) return { status: 'discarded' }
        emit.success('Connection test successful')
        return { status: 'accepted' }
      }
      if (!ownsSlot(slot, token)) return { status: 'discarded' }
      emit.success('Connection test successful')
      await refresh()
      return { status: 'accepted' }
    } catch (cause) {
      if (!ownsSlot(slot, token)) return { status: 'discarded' }
      handleError(key, cause)
      await refresh()
      return { status: 'accepted' }
    } finally {
      // Release only THIS command's token: a superseded command never
      // releases the row's remaining busy state, and a disposed owner
      // touches nothing.
      if (!disposed) releaseBusy(key, token)
    }
  }

  async function revokeConnection(key: BrokerConnectionKey): Promise<{ status: 'accepted' | 'discarded' }> {
    const slot = `${brokerKey(key)}:revoke`
    if (disposed) return { status: 'discarded' }
    const token = claimSlot(slot)
    acquireBusy(key, token)
    rowErrors.delete(brokerKey(key))
    try {
      await revokeTokenApi(key.provider, key.tokenId)
      if (!ownsSlot(slot, token)) return { status: 'discarded' }
      emit.success('Token revoked successfully')
      await refresh()
      return { status: 'accepted' }
    } catch (cause) {
      if (!ownsSlot(slot, token)) return { status: 'discarded' }
      handleError(key, cause)
      return { status: 'accepted' }
    } finally {
      if (!disposed) releaseBusy(key, token)
    }
  }

  function requestDelete(key: BrokerConnectionKey): void {
    const row = lists.value
      .get(key.provider)
      ?.find((record) => record.id === key.tokenId)
    const label = row ? toDisplay(key.provider, row, false).label : `#${key.tokenId}`
    const providerName =
      key.provider === 'ib' ? 'Interactive Brokers' : key.provider === 'tinkoff' ? 'Tinkoff' : key.provider === 'bybit' ? 'Bybit' : 'OKX'
    deleteCandidate.value = {
      key: { provider: key.provider, tokenId: key.tokenId },
      subject: `${providerName} · ${label} (#${key.tokenId})`,
    }
  }

  function cancelDelete(): void {
    deleteCandidate.value = null
  }

  async function confirmDelete(): Promise<void> {
    const candidate = deleteCandidate.value
    if (!candidate || deleteBusy || disposed) return
    deleteBusy = true
    rowErrors.delete(brokerKey(candidate.key))
    try {
      await deleteTokenApi(candidate.key.provider, candidate.key.tokenId)
      if (disposed) return
      emit.success('Token deleted successfully')
      deleteCandidate.value = null
      await refresh()
    } catch (cause) {
      if (disposed) return
      // The snapshot stays so a retry targets the same connection.
      handleError(candidate.key, cause)
    } finally {
      deleteBusy = false
    }
  }

  async function runTinkoffPostSaveTest(tokenId: number): Promise<void> {
    const key: BrokerConnectionKey = { provider: 'tinkoff', tokenId }
    const slot = `${brokerKey(key)}:test`
    const token = claimSlot(slot)
    acquireBusy(key, token)
    try {
      await testTinkoffConnection(tokenId)
      if (!ownsSlot(slot, token)) return
      emit.success('Connection test successful')
    } catch (cause) {
      if (!ownsSlot(slot, token)) return
      handleError(key, cause)
    } finally {
      if (!disposed) releaseBusy(key, token)
      if (ownsSlot(slot, token)) await refresh()
    }
  }

  async function saveConnection(draft: BrokerCredentialDraft): Promise<BrokerSaveOutcome> {
    if (disposed) return 'rejected'
    const generation = ++saveGeneration
    const stale = (): boolean => disposed || generation !== saveGeneration
    try {
      if (draft.provider === 'tinkoff') {
        const response = (await saveTinkoffToken({
          broker: draft.brokerId,
          token: draft.token,
          token_type: draft.tokenType,
          sandbox_mode: draft.sandboxMode,
        })) as { message?: string; id?: number }
        if (stale()) return 'rejected'
        if (typeof response.message === 'string' && response.message.includes('reactivated')) {
          messageDialog.value = {
            title: 'Token Reactivated',
            text: response.message,
          }
          await refresh()
          return 'reactivated'
        }
        if (typeof response.message === 'string') emit.success(response.message)
        if (typeof response.id === 'number') await runTinkoffPostSaveTest(response.id)
        if (stale()) return 'rejected'
        await refresh()
        return 'saved'
      }
      if (draft.provider === 'ib') {
        await saveIBToken({
          broker: draft.brokerId,
          token: draft.token,
          account_id: draft.accountId,
          paper_trading: draft.paperTrading,
        })
      } else if (draft.provider === 'bybit') {
        await saveBybitToken({
          broker: draft.brokerId,
          api_key: draft.apiKey,
          api_secret: draft.apiSecret,
          testnet: draft.testnet,
        })
      } else {
        await saveOKXToken({
          broker: draft.brokerId,
          api_key: draft.apiKey,
          api_secret: draft.apiSecret,
          passphrase: draft.passphrase,
          simulated_trading: draft.simulatedTrading,
        })
      }
      if (stale()) return 'rejected'
      emit.success(
        draft.provider === 'ib'
          ? 'Token saved successfully'
          : draft.provider === 'bybit'
            ? 'Bybit token saved successfully'
            : 'OKX token saved successfully',
      )
      await refresh()
      return 'saved'
    } catch (cause) {
      if (stale()) return 'rejected'
      const alreadyActive = isAlreadyActive(cause)
      if (alreadyActive !== null) {
        messageDialog.value = { title: 'Token Already Exists', text: alreadyActive }
        return 'already-active'
      }
      handleError(null, cause)
      return 'rejected'
    }
  }

  const connections = computed<readonly BrokerConnectionDisplay[]>(() => {
    const rows: BrokerConnectionDisplay[] = []
    const order: BrokerProvider[] = ['tinkoff', 'ib', 'bybit', 'okx']
    for (const provider of order) {
      const records = lists.value.get(provider) ?? []
      const visible = showInactive.value
        ? records
        : records.filter((record) => record.is_active)
      for (const record of visible) {
        if (!isBrokerProvider(provider)) continue
        rows.push(toDisplay(provider, record, isBusy({ provider, tokenId: record.id })))
      }
    }
    return rows
  })

  return {
    loading,
    connections,
    showInactive,
    brokerOptions,
    messageDialog,
    deleteCandidate,
    isBusy,
    rowError,
    refresh,
    loadBrokers,
    testConnection,
    revokeConnection,
    requestDelete,
    cancelDelete,
    confirmDelete,
    saveConnection,
    dismissMessageDialog: (): void => {
      messageDialog.value = null
    },
  }
}
