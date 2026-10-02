// Chart contract v2 typed boundary (C2). The interfaces mirror the merged C1
// wire authority (backend/services/charts.py, backend/dashboard/views.py,
// backend/database/views.py). Decimal strings stay strings through validation,
// state and adapters; no frontend financial arithmetic happens here. The
// generated api.d.ts does not describe chartV2, so this boundary is
// handwritten and runtime-checked in parseChartEnvelope.ts.
import type { PortfolioContext } from '@/types/portfolioContext'

export type DecimalString = string
export type ISODate = string
export type Frequency = 'D' | 'W' | 'M' | 'Q' | 'Y'
export type NavMode =
  | 'none'
  | 'account'
  | 'asset_type'
  | 'asset_class'
  | 'currency'
  | 'value_contributions'
  | 'value_contributions_cumulative'
export type ValueStatus = 'ok' | 'partial' | 'unknown' | 'not_available' | 'not_relevant'
export type ChartValueReason =
  | 'observed'
  | 'zero_exposure'
  | 'missing_price'
  | 'missing_fx'
  | 'omitted_valuation'
  | 'absent_unclassified'
  | 'solver_unavailable'
  | 'not_relevant'

export interface ChartValue {
  /** Raw complete value in the series' stated unit; null for non-ok status. */
  value: DecimalString | null
  /** Backend-scaled plotting value; null for non-ok status. */
  plotValue: DecimalString | null
  /** Permitted only for partial; never a complete NAV. */
  knownSubtotal?: DecimalString
  status: ValueStatus
  reason: ChartValueReason
  /** Exact user-facing value; never parsed by the client. */
  display: string
}

export type ChartUnit =
  | { kind: 'money'; currency: string; plotDivisor: '1' | '1000' }
  | { kind: 'ratio'; plotDivisor: '1' }
  | { kind: 'quantity'; plotDivisor: '1' }
  | { kind: 'percent_of_nominal'; plotDivisor: '1' }

export interface ChartPeriod {
  /** Server identity; unique even for repeated display labels or dates. */
  key: string
  /** Actual sampled endpoint, never reconstructed from a label. */
  endDate: ISODate
  displayLabel: string
  interval: {
    /** null means the existing first-point inception horizon. */
    startDate: ISODate | null
    endDate: ISODate
    kind: 'inception' | 'sample_interval'
  }
  /** Calendar bucket incomplete, not valuation completeness. */
  partialPeriod: boolean
}

export type ChartSeriesMetric =
  | 'nav'
  | 'category_nav'
  | 'opening_nav'
  | 'contributions'
  | 'return'
  | 'net_investments'
  | 'irr_inception'
  | 'irr_interval'
  | 'price'
  | 'position'

export interface ChartSeriesCategory {
  kind: 'account_group' | 'asset_type' | 'asset_class' | 'currency'
  code?: string
  memberAccountIds?: readonly number[]
}

export interface ChartSeries {
  /** Server-issued canonical identity. */
  id: string
  label: string
  metric: ChartSeriesMetric
  /** Cartesian role; allocation slices come from allocations, not roles. */
  role: 'bar' | 'line'
  axis: 'money' | 'return' | 'price' | 'quantity'
  unit: ChartUnit
  points: readonly ChartValue[]
  category?: ChartSeriesCategory
}

export type ChartPartition = 'complete' | 'legacy_non_partitioning' | 'unknown'
export type PieEligibility = 'eligible' | 'signed' | 'nonpositive_total' | 'incomplete' | 'nonpartitioning'
export type AllocationDimension = 'asset_type' | 'asset_class' | 'currency'

export interface ChartAllocation {
  seriesId: string
  rank: number
  amount: ChartValue
  share: ChartValue
}

export interface ChartAllocationSummary {
  dimension: AllocationDimension
  /** Always reporting-currency money with divisor 1. */
  unit: Extract<ChartUnit, { kind: 'money' }>
  /** Full reporting NAV, never a selected/visible subtotal. */
  denominator: ChartValue
  /** Raw ratio 1 only for a known complete positive-NAV partition. */
  totalShare: ChartValue
  pieEligibility: PieEligibility
}

export interface ChartDocumentContext {
  accountSelection: PortfolioContext['accountSelection']
  accountIds: readonly number[]
  effectiveDate: ISODate
  currency: string
  digits: number
}

export interface ChartDocument {
  version: 2
  kind: 'nav' | 'allocation' | 'price' | 'position'
  outcome: 'ready' | 'empty' | 'partial'
  context: ChartDocumentContext
  /** Required for price/position. */
  security?: { id: number; instrumentType: string }
  periods: readonly ChartPeriod[]
  series: readonly ChartSeries[]
  /** Full NAV, never a frontend sum of selected bars. */
  totals?: readonly ChartValue[]
  allocations?: readonly ChartAllocation[]
  /** Required with allocations when kind === 'allocation'. */
  allocationSummary?: ChartAllocationSummary
  partition: ChartPartition
}

export interface ChartErrorBody {
  error: {
    code: 'INVALID_CHART_QUERY' | 'CHART_CALCULATION_FAILED'
    message: string
    retryable: boolean
  }
}

export type ReadyChartContext = PortfolioContext & { effectiveCurrentDate: ISODate; currency: string }

export interface NavQuery {
  context: ReadyChartContext
  mode: NavMode
  frequency: Frequency
  fromDate: ISODate | null
  toDate: ISODate
}

export interface LegacyNavDataset {
  label: string
  /** Some incumbent servers omit type; validated when present, never coerced. */
  type?: 'bar' | 'line'
  data: readonly (number | string | null)[]
  [key: string]: unknown
}

export interface LegacyNav {
  labels: readonly string[]
  datasets: readonly LegacyNavDataset[]
  currency: string
  /** Legacy envelopes may carry extra fields (e.g. empty); they survive as-is. */
  [key: string]: unknown
}

export type NavResult =
  | { capability: 'v2'; legacy: LegacyNav; document: ChartDocument }
  | { capability: 'legacy_only'; legacy: LegacyNav }
