// D4 — pure position-table view model. Preset definitions and ordered
// visible-column/header derivation over the leaf metadata in
// positionsHeaders.js. No component, store or persistence concerns here.
import {
  closedPositionsHeaders,
  flattenHeaders,
  openPositionsHeaders,
} from '@/config/positionsHeaders'

export type PositionTableId = 'open-positions' | 'closed-positions'
export type PositionPresetId = 'overview' | 'comparison' | 'full-ledger' | 'custom'
export type PositionGroupId = 'identity' | 'entry' | 'current' | 'exit' | 'performance'
export type PositionUnitKind =
  | 'identity'
  | 'date'
  | 'quantity'
  | 'instrument-price'
  | 'reporting-money'
  | 'ratio'

// The security name is the one leaf that can never be hidden: every view
// keeps a row identity.
export const POSITION_IDENTITY_KEY = 'name'

export const POSITION_GROUP_ORDER: readonly PositionGroupId[] = [
  'identity', 'entry', 'current', 'exit', 'performance',
]

const GROUP_TITLES: Record<PositionGroupId, string> = {
  identity: 'Identity',
  entry: 'Entry',
  current: 'Current',
  exit: 'Exit',
  performance: 'Performance',
}

interface LeafMetadata {
  key: string
  title: string
  fullTitle: string
  groupId: PositionGroupId
  unitKind: PositionUnitKind
  description: string
  align: 'start' | 'center' | 'end'
  sortable: boolean
  identity: boolean
  pinned: boolean
  class?: string
}

const TABLE_HEADERS: Record<PositionTableId, typeof openPositionsHeaders> = {
  'open-positions': openPositionsHeaders,
  'closed-positions': closedPositionsHeaders,
}

// Ordered leaf registry per table: canonical order is the original header
// order (identity leaves first, then entry/current|exit, then performance).
function leafRegistry(tableId: PositionTableId): LeafMetadata[] {
  return flattenHeaders(TABLE_HEADERS[tableId]).map((leaf) => ({
    key: String(leaf.key),
    title: String(leaf.title),
    fullTitle: String(leaf.fullTitle),
    groupId: leaf.groupId as PositionGroupId,
    unitKind: leaf.unitKind as PositionUnitKind,
    description: String(leaf.description ?? ''),
    align: (leaf.align ?? 'end') as LeafMetadata['align'],
    sortable: leaf.sortable !== false,
    identity: leaf.identity === true,
    pinned: leaf.pinned === true,
    class: leaf.class,
  }))
}

export function positionTableLeaves(tableId: PositionTableId): LeafMetadata[] {
  return leafRegistry(tableId)
}

export interface PositionPresetDefinition {
  id: Exclude<PositionPresetId, 'custom'>
  label: string
  description: string
  /** null = every original leaf (Full ledger). */
  keys: readonly string[] | null
  /** Overview renders one flat header row with qualified labels. */
  flat: boolean
}

const OPEN_OVERVIEW_KEYS: readonly string[] = [
  'name', 'currency', 'entry_value', 'current_value', 'share_of_portfolio',
  'total_return_amount', 'total_return_percentage', 'irr',
]
const CLOSED_OVERVIEW_KEYS: readonly string[] = [
  'name', 'currency', 'entry_value', 'exit_value',
  'total_return_amount', 'total_return_percentage', 'irr',
]
const OPEN_COMPARISON_KEYS: readonly string[] = [
  'name', 'currency', 'investment_date', 'entry_price', 'entry_value',
  'current_price', 'current_value', 'share_of_portfolio',
]
const CLOSED_COMPARISON_KEYS: readonly string[] = [
  'name', 'currency', 'investment_date', 'entry_value', 'exit_date', 'exit_value',
]

const PRESETS: Record<PositionTableId, readonly PositionPresetDefinition[]> = {
  'open-positions': [
    {
      id: 'overview', label: 'Overview', keys: OPEN_OVERVIEW_KEYS, flat: true,
      description: 'Which holdings need attention: value, share and total return.',
    },
    {
      id: 'comparison', label: 'Entry & valuation', keys: OPEN_COMPARISON_KEYS, flat: false,
      description: 'Compare acquisition with the current valuation side by side.',
    },
    {
      id: 'full-ledger', label: 'Full ledger', keys: null, flat: false,
      description: 'Reconcile all 20 financial components in two grouped header rows.',
    },
  ],
  'closed-positions': [
    {
      id: 'overview', label: 'Overview', keys: CLOSED_OVERVIEW_KEYS, flat: true,
      description: 'Which holdings need attention: value and total return.',
    },
    {
      id: 'comparison', label: 'Entry & exit', keys: CLOSED_COMPARISON_KEYS, flat: false,
      description: 'Compare acquisition with the disposal side by side.',
    },
    {
      id: 'full-ledger', label: 'Full ledger', keys: null, flat: false,
      description: 'Reconcile all 16 financial components in two grouped header rows.',
    },
  ],
}

export function positionPresets(tableId: PositionTableId): readonly PositionPresetDefinition[] {
  return PRESETS[tableId]
}

export function positionPresetLabel(tableId: PositionTableId, preset: PositionPresetId): string {
  if (preset === 'custom') return 'Custom'
  return PRESETS[tableId].find((definition) => definition.id === preset)?.label ?? 'Custom'
}

export interface PositionViewLeaf {
  key: string
  title: string
  fullTitle: string
  groupId: PositionGroupId
  groupTitle: string
  isFirstOfGroup: boolean
  unitKind: PositionUnitKind
  /** Reporting-currency code for money leaves, '%' for ratios, '' otherwise. */
  unitLabel: string
  description: string
  align: 'start' | 'center' | 'end'
  sortable: boolean
  identity: boolean
  pinned: boolean
  headerId: string
  class?: string
}

export interface PositionViewGroup {
  id: PositionGroupId
  title: string
  keys: string[]
}

export interface PositionHeaderCell {
  key: string
  title: string
  colspan: number
  align: 'start' | 'center' | 'end'
}

export interface PositionView {
  tableId: PositionTableId
  preset: PositionPresetId
  flat: boolean
  leaves: PositionViewLeaf[]
  leafKeys: string[]
  groups: PositionViewGroup[]
  /** One (flat) or two (banded) structural header rows. */
  headerRows: PositionHeaderCell[][]
}

function unitLabelFor(unitKind: PositionUnitKind, currency: string): string {
  switch (unitKind) {
    case 'reporting-money': return currency
    case 'instrument-price': return 'security currency'
    case 'ratio': return '%'
    case 'quantity': return 'units'
    default: return ''
  }
}

function headerIdFor(tableId: PositionTableId, key: string): string {
  return `${tableId}-${key}`
}

function resolveVisibleKeys(
  tableId: PositionTableId,
  preset: PositionPresetId,
  visibleKeys: readonly string[] | null,
): string[] {
  if (preset !== 'custom') {
    const definition = PRESETS[tableId].find((entry) => entry.id === preset)
    if (!definition) return [POSITION_IDENTITY_KEY]
    if (definition.keys === null) return leafRegistry(tableId).map((leaf) => leaf.key)
    return [...definition.keys]
  }
  const known = new Set(leafRegistry(tableId).map((leaf) => leaf.key))
  const selected = new Set<string>()
  for (const key of visibleKeys ?? []) {
    if (known.has(key)) selected.add(key)
  }
  selected.add(POSITION_IDENTITY_KEY)
  // Canonical order inside each group regardless of selection order.
  return leafRegistry(tableId)
    .map((leaf) => leaf.key)
    .filter((key) => selected.has(key))
}

export function buildPositionView(
  tableId: PositionTableId,
  preset: PositionPresetId,
  visibleKeys: readonly string[] | null,
  currency: string,
): PositionView {
  const registry = leafRegistry(tableId)
  const keys = resolveVisibleKeys(tableId, preset, visibleKeys)
  const leafByKey = new Map(registry.map((leaf) => [leaf.key, leaf]))

  const groupOrder = POSITION_GROUP_ORDER.filter((groupId) =>
    keys.some((key) => leafByKey.get(key)?.groupId === groupId),
  )
  const groups: PositionViewGroup[] = groupOrder.map((groupId) => ({
    id: groupId,
    title: GROUP_TITLES[groupId],
    keys: keys.filter((key) => leafByKey.get(key)?.groupId === groupId),
  }))
  const firstOfGroup = new Set(groups.map((group) => group.keys[0]))

  const flat = preset === 'overview'
  const leaves: PositionViewLeaf[] = keys.map((key) => {
    const leaf = leafByKey.get(key)!
    return {
      key: leaf.key,
      title: leaf.title,
      fullTitle: leaf.fullTitle,
      groupId: leaf.groupId,
      groupTitle: GROUP_TITLES[leaf.groupId],
      isFirstOfGroup: firstOfGroup.has(key),
      unitKind: leaf.unitKind,
      unitLabel: unitLabelFor(leaf.unitKind, currency),
      description: leaf.description.replaceAll('{currency}', currency),
      align: leaf.align,
      sortable: leaf.sortable,
      identity: leaf.identity,
      pinned: leaf.pinned,
      headerId: headerIdFor(tableId, key),
      class: leaf.class,
    }
  })

  const headerRows: PositionHeaderCell[][] = flat
    ? [leaves.map((leaf) => ({ key: leaf.key, title: leaf.fullTitle, colspan: 1, align: leaf.align }))]
    : [
        groups.map((group) => ({
          key: group.id,
          title: group.title,
          colspan: group.keys.length,
          align: 'start' as const,
        })),
        leaves.map((leaf) => ({ key: leaf.key, title: leaf.title, colspan: 1, align: leaf.align })),
      ]

  return { tableId, preset, flat, leaves, leafKeys: keys, groups, headerRows }
}
