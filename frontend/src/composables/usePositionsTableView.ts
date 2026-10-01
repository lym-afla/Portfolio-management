// D4 — per-table, per-user presentation preferences for the position tables.
// Presentation state only: sort/search/page query settings stay in the app
// store's table settings; this composable never issues or owns requests.
// The saved view is written ONLY on explicit user actions (preset switch,
// column toggle, reset); resize and route changes never mutate it.
import { computed, ref, watch, type Ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import {
  buildPositionView,
  positionPresets,
  POSITION_IDENTITY_KEY,
  type PositionPresetId,
  type PositionTableId,
} from '@/config/positionsTableViews'

const STORAGE_VERSION = 1

interface StoredView {
  version: number
  preset: PositionPresetId
  visibleKeys: string[]
}

const PRESET_IDS: readonly PositionPresetId[] = ['overview', 'comparison', 'full-ledger', 'custom']

function storageKeyFor(userKey: string, tableId: PositionTableId): string {
  return `positionsTableView.v${STORAGE_VERSION}.${userKey}.${tableId}`
}

// Stable user scope from the authenticated profile identity — never access
// tokens (they rotate) or display names.
function userKeyOf(user: unknown): string | null {
  if (user === null || user === undefined) return null
  const record = user as { id?: unknown; username?: unknown }
  if (record.id !== undefined && record.id !== null) return `u${String(record.id)}`
  if (record.username) return `u${String(record.username)}`
  return null
}

function readStoredView(userKey: string, tableId: PositionTableId): StoredView | null {
  let raw: string | null
  try {
    raw = localStorage.getItem(storageKeyFor(userKey, tableId))
  } catch {
    return null
  }
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null
  const candidate = parsed as Partial<StoredView>
  if (candidate.version !== STORAGE_VERSION) return null
  if (!PRESET_IDS.includes(candidate.preset as PositionPresetId)) return null
  if (candidate.preset === 'custom' && !Array.isArray(candidate.visibleKeys)) return null
  const visibleKeys = Array.isArray(candidate.visibleKeys)
    ? candidate.visibleKeys.filter((key): key is string => typeof key === 'string')
    : undefined
  if (visibleKeys !== undefined && new Set(visibleKeys).size !== visibleKeys.length) return null
  return {
    version: STORAGE_VERSION,
    preset: candidate.preset as PositionPresetId,
    visibleKeys: visibleKeys ?? [],
  }
}

function canonicalKeys(tableId: PositionTableId, preset: PositionPresetId, visibleKeys: readonly string[]): string[] {
  return buildPositionView(tableId, preset, visibleKeys, 'USD').leafKeys
}

export function usePositionsTableView(tableId: PositionTableId) {
  const authStore = useAuthStore()
  const { user } = storeToRefs(authStore)

  const preset = ref<PositionPresetId>('overview')
  const visibleKeys = ref<string[]>(canonicalKeys(tableId, 'overview', []))
  // Starts null so the immediate watch below performs the initial load for
  // the current identity (and resets to Overview when there is none).
  const currentUserKey = ref<string | null>(null)

  const storageAvailable = () => {
    try {
      return typeof localStorage !== 'undefined'
    } catch {
      return false
    }
  }

  const persist = () => {
    const userKey = currentUserKey.value
    if (!userKey || !storageAvailable()) return
    const payload: StoredView = {
      version: STORAGE_VERSION,
      preset: preset.value,
      visibleKeys: visibleKeys.value,
    }
    try {
      localStorage.setItem(storageKeyFor(userKey, tableId), JSON.stringify(payload))
    } catch {
      /* Unavailable storage degrades to in-memory preferences. */
    }
  }

  const load = (userKey: string | null) => {
    const stored = userKey ? readStoredView(userKey, tableId) : null
    if (!stored) {
      preset.value = 'overview'
      visibleKeys.value = canonicalKeys(tableId, 'overview', [])
      return
    }
    preset.value = stored.preset
    visibleKeys.value = canonicalKeys(tableId, stored.preset, stored.visibleKeys)
  }

  const setPreset = (next: PositionPresetId) => {
    if (!PRESET_IDS.includes(next)) return
    preset.value = next
    visibleKeys.value = canonicalKeys(tableId, next, visibleKeys.value)
    persist()
  }

  const toggleColumn = (key: string) => {
    if (key === POSITION_IDENTITY_KEY) return
    const next = new Set(visibleKeys.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    next.add(POSITION_IDENTITY_KEY)
    preset.value = 'custom'
    visibleKeys.value = canonicalKeys(tableId, 'custom', [...next])
    persist()
  }

  const resetView = () => {
    preset.value = 'overview'
    visibleKeys.value = canonicalKeys(tableId, 'overview', [])
    persist()
  }

  // Session changes: reload (or reset) when the authenticated identity
  // changes — including logout, which clears to Overview in memory without
  // touching any user's stored preferences.
  watch(
    user,
    (nextUser) => {
      const nextKey = userKeyOf(nextUser)
      if (nextKey === currentUserKey.value) return
      currentUserKey.value = nextKey
      load(nextKey)
    },
    { immediate: true },
  )

  const isColumnVisible = (key: string) => visibleKeys.value.includes(key)

  const viewFor = (currency: string) =>
    computed(() => buildPositionView(tableId, preset.value, visibleKeys.value, currency))

  const presetOptions = positionPresets(tableId)

  return {
    preset: preset as Ref<PositionPresetId>,
    visibleKeys: visibleKeys as Ref<string[]>,
    setPreset,
    toggleColumn,
    resetView,
    isColumnVisible,
    viewFor,
    presetOptions,
  }
}
