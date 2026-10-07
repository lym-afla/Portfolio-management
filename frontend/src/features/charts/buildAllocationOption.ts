// Pure ECharts option construction for the allocation pies (C4). Type-only
// ECharts import: no ECharts runtime enters this module — the lazy
// EChartsAllocation component owns the runtime.
//
// Server certification is the whole contract: only documents whose
// allocationSummary.pieEligibility is 'eligible' produce a pie (one series,
// zero inner radius, slices in server rank order colored by stable server-ID
// hashes shared with NAV). toPlotNumber is used ONLY at the geometry
// boundary; labels, tooltips, shares and the full-NAV denominator stay exact
// server strings, and ECharts' own params.percent is never shown. The
// built-in canvas legend and slice selection are disabled — highlighting is
// an HTML-legend interaction (AllocationLegend) that cannot change geometry.
// Signed, incomplete, nonpartitioning and nonpositive allocations produce no
// pie at all: buildAllocationOption returns null and the panel states the
// server-certified reason beside the complete exact table.
import type { EChartsOption } from 'echarts'
import type { PieSeriesOption } from 'echarts/charts'
import type { ChartAllocation, ChartDocument, ChartValue } from './contracts'
import { toPlotNumber } from './renderBoundary'
import { seriesColor } from './seriesStyles'
import { allocationTooltipPosition } from './tooltipPlacement'

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Exact server text for a value; unavailable values state their status. */
function valueLine(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? `; known subtotal ${point.knownSubtotal}` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}

export function allocationEligible(document: ChartDocument): boolean {
  return (
    document.kind === 'allocation' &&
    document.allocationSummary?.pieEligibility === 'eligible' &&
    (document.allocations?.length ?? 0) > 0
  )
}

/** Concise, server-certified reason a pie must not be drawn. */
export function allocationIneligibilityReason(document: ChartDocument): string {
  if (document.outcome === 'empty' || (document.allocations?.length ?? 0) === 0) {
    return 'No data for the selected account and period. Adjust the date range or select another account.'
  }
  switch (document.allocationSummary?.pieEligibility) {
    case 'signed':
      return 'Some positions are negative, so a share pie would be misleading. Exact signed values are in the Table view.'
    case 'nonpositive_total':
      return 'The total NAV is zero or negative, so allocation shares are not defined. Exact values are in the Table view.'
    case 'incomplete':
      return 'Some valuations are missing, so the allocation is incomplete. Exact known values and statuses are in the Table view.'
    case 'nonpartitioning':
      return 'The categories do not add up to the full NAV (some holdings are unclassified or unvalued), so a share pie would be misleading. Exact values are in the Table view.'
    default:
      return 'This allocation cannot be drawn as a pie. Exact values are in the Table view.'
  }
}

function allocationTooltip(document: ChartDocument, params: unknown): string {
  const index = typeof (params as { dataIndex?: unknown }).dataIndex === 'number'
    ? (params as { dataIndex: number }).dataIndex
    : -1
  const allocation: ChartAllocation | undefined = document.allocations?.[index]
  if (!allocation) return ''
  const label = document.series.find((series) => series.id === allocation.seriesId)?.label ?? allocation.seriesId
  const summary = document.allocationSummary
  const lines = [`<strong>${escapeHtml(label)}</strong>`]
  lines.push(`Amount: ${escapeHtml(valueLine(allocation.amount))}`)
  lines.push(`Share: ${escapeHtml(valueLine(allocation.share))}`)
  if (summary) {
    lines.push(`Full-NAV denominator: ${escapeHtml(valueLine(summary.denominator))}`)
    lines.push(`Total of categories: ${escapeHtml(valueLine(summary.totalShare))}`)
  }
  return lines.join('<br/>')
}

export function buildAllocationOption(
  document: ChartDocument,
  resolveContainer?: () => HTMLElement | null,
): EChartsOption | null {
  if (!allocationEligible(document)) return null
  const summary = document.allocationSummary!
  const labelById = new Map(document.series.map((series) => [series.id, series.label]))
  // Eligibility is parser-certified: every contributing amount is ok, so the
  // plotting boundary never yields null here (a null would be a renderer
  // failure surfaced by the RangeError path, never a silent gap).
  const data = document.allocations!.map((allocation) => ({
    id: allocation.seriesId,
    name: labelById.get(allocation.seriesId) ?? allocation.seriesId,
    value: toPlotNumber(allocation.amount) as number,
    itemStyle: { color: seriesColor(allocation.seriesId) },
  }))
  const series: PieSeriesOption[] = [
    {
      id: `allocation-pie:${summary.dimension}`,
      name: summary.dimension,
      type: 'pie',
      radius: [0, '68%'],
      center: ['50%', '50%'],
      selectedMode: false,
      // Percent labels derived from geometry are forbidden; the category
      // name is server identity, exact shares live in tooltips and table.
      label: { formatter: '{b}' },
      data,
    },
  ]
  return {
    aria: { enabled: true },
    animation: false,
    // Viewport containment is not visibility (see buildNavOption): the
    // tooltip renders into document.body and the position callback pins it
    // inside the unobscured viewport band, below the fixed workspace header.
    tooltip: {
      trigger: 'item',
      className: 'allocation-chart-tooltip',
      extraCssText: 'max-width: min(340px, 92vw); white-space: normal; overflow-wrap: break-word;',
      appendTo: () => globalThis.document.body,
      position: (point, params, dom, rect, size) => allocationTooltipPosition({
        point,
        dom: dom instanceof HTMLElement ? dom : null,
        size,
        resolveContainer,
      }),
      formatter: (params: unknown) => allocationTooltip(document, params),
    },
    series,
  }
}
