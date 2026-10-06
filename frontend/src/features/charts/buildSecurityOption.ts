// Pure ECharts option construction for the security histories (C4). Type-only
// ECharts import: no ECharts runtime enters this module — the lazy
// EChartsSecurity component owns the runtime.
//
// Server order and identity are the whole contract: the category axis is
// keyed by the server period keys (same-date events stay distinct
// categories), the line is unsmoothed with connectNulls false, and the
// position line steps from end to end so discrete holdings never suggest a
// gradual change. The y-axis name comes from the series unit metadata —
// instrument currency or percent-of-nominal for prices, quantity for
// positions — and values are NEVER rescaled (a bond price 98.5 plots as
// 98.5). toPlotNumber is the only numeric boundary; tooltips and tables stay
// exact server strings.
//
// Effective-date carry-forward is presentation-only: when the document's
// last observation ends before the request's effective date and that
// observation has a known value, the plot gains ONE extra endpoint at the
// effective date carrying that value, annotated as carried forward from its
// source date. It is never a future quote, never replaces an identical
// endpoint, and never enters the validated document or the observed-point
// table (SecurityDataTable reads the document only).
import type { EChartsOption } from 'echarts'
import type { ChartDocument, ChartValue } from './contracts'
import { toPlotNumber } from './renderBoundary'
import { seriesColor } from './seriesStyles'
import { securityTooltipPosition } from './tooltipPlacement'

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Axis name: prices state their unit kind, positions their quantity. */
export function securityAxisName(document: ChartDocument): string {
  const unit = document.series[0]?.unit
  if (!unit) return ''
  if (unit.kind === 'money') return unit.currency
  if (unit.kind === 'percent_of_nominal') return '% of nominal'
  return 'quantity'
}

/** Exact server text for a value; unavailable values state their status. */
function valueLine(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? `; known subtotal ${point.knownSubtotal}` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}

const CARRY_FORWARD_PREFIX = 'carry-forward:'

interface TooltipParam {
  dataIndex?: number
  axisValue?: string
}

function securityTooltip(document: ChartDocument, params: unknown): string {
  const list = Array.isArray(params) ? (params as TooltipParam[]) : [params as TooltipParam]
  const index = typeof list[0]?.dataIndex === 'number' ? list[0].dataIndex : -1
  const key = list[0]?.axisValue
  const series = document.series[0]
  if (!series || index < 0) return ''
  const period = document.periods[index]
  const lines: string[] = []
  if (period) {
    lines.push(`<strong>${escapeHtml(period.displayLabel)} (${escapeHtml(period.endDate)})</strong>`)
    lines.push(`${escapeHtml(series.label)}: ${escapeHtml(valueLine(series.points[index]))}`)
  } else if (typeof key === 'string' && key.startsWith(CARRY_FORWARD_PREFIX)) {
    const source = document.periods[document.periods.length - 1]
    const sourceDate = source?.endDate ?? ''
    lines.push(`<strong>${escapeHtml(key.slice(CARRY_FORWARD_PREFIX.length))}</strong>`)
    lines.push(
      `${escapeHtml(series.label)}: ${escapeHtml(valueLine(series.points[series.points.length - 1]))}`,
    )
    lines.push(`<em>carried forward from ${escapeHtml(sourceDate)} (presentation-only, not an observed quote)</em>`)
  }
  return lines.join('<br/>')
}

export interface SecurityViewport {
  viewport: { firstPeriodKey: string; lastPeriodKey: string } | null
}

export function buildSecurityOption(
  document: ChartDocument,
  interaction: SecurityViewport = { viewport: null },
  resolveContainer?: () => HTMLElement | null,
): EChartsOption {
  const series = document.series[0]
  if (!series) {
    return { xAxis: { type: 'category', data: [] }, yAxis: { type: 'value' }, series: [] }
  }
  const labelsByKey = new Map(document.periods.map((period) => [period.key, period.displayLabel]))
  const axisKeys = document.periods.map((period) => period.key)
  const data = document.periods.map((_period, index) => toPlotNumber(series.points[index]))
  // Presentation-only carry-forward of the last known observation to the
  // request's effective date (see module comment for the exact conditions).
  let carriedForwardKey: string | null = null
  if (carriesForwardTo(document)) {
    const key = `${CARRY_FORWARD_PREFIX}${document.context.effectiveDate}`
    axisKeys.push(key)
    data.push(toPlotNumber(series.points[series.points.length - 1]))
    carriedForwardKey = key
  }
  let startValue = 0
  let endValue = 100
  const periodCount = axisKeys.length
  if (interaction.viewport && periodCount > 1) {
    const first = axisKeys.indexOf(interaction.viewport.firstPeriodKey)
    const last = axisKeys.indexOf(interaction.viewport.lastPeriodKey)
    if (first >= 0 && last >= 0 && first <= last) {
      startValue = (first / (periodCount - 1)) * 100
      endValue = (last / (periodCount - 1)) * 100
    }
  }
  const option: Record<string, unknown> = {
    aria: { enabled: true },
    animation: false,
    // Viewport containment is not visibility (see buildNavOption): the
    // tooltip renders into document.body and the position callback pins it
    // inside the unobscured viewport band, below the fixed workspace header.
    tooltip: {
      trigger: 'axis',
      className: 'security-chart-tooltip',
      extraCssText: 'max-width: min(340px, 92vw); white-space: normal; overflow-wrap: break-word;',
      appendTo: () => globalThis.document.body,
      position: (
        point: { x: number; y: number } | number[],
        params: unknown,
        dom: HTMLElement | null,
        rect: unknown,
        size: { contentSize: number[]; viewSize: number[] },
      ) => securityTooltipPosition({
        point,
        dom: dom instanceof HTMLElement ? dom : null,
        size,
        resolveContainer,
      }),
      formatter: (params: unknown) => securityTooltip(document, params),
    },
    xAxis: {
      type: 'category',
      data: axisKeys,
      axisLabel: { formatter: (value: string) => labelsByKey.get(value) ?? value },
    },
    yAxis: {
      type: 'value',
      name: securityAxisName(document),
      // Positions start at zero (incumbent parity); prices scale to the data.
      ...(document.kind === 'position' ? { min: 0 } : { scale: true }),
    },
    dataZoom: [
      { type: 'inside', start: startValue, end: endValue },
      { type: 'slider', start: startValue, end: endValue },
    ],
    series: [
      {
        id: series.id,
        name: series.label,
        type: 'line',
        // Positions step from end to end; prices stay an unsmoothed line.
        ...(document.kind === 'position' ? { step: 'end' as const } : {}),
        connectNulls: false,
        smooth: false,
        itemStyle: { color: seriesColor(series.id) },
        lineStyle: { color: seriesColor(series.id) },
        data,
      },
    ],
  }
  void carriedForwardKey
  return option as EChartsOption
}

/** The synthetic carry-forward endpoint appended by buildSecurityOption, if
    any — presentation-only identity used by evidence probes, never by the
    validated document or the observed-point table. */
export function securityCarryForwardKey(document: ChartDocument): string | null {
  if (!carriesForwardTo(document)) return null
  return `${CARRY_FORWARD_PREFIX}${document.context.effectiveDate}`
}

function carriesForwardTo(document: ChartDocument): boolean {
  const series = document.series[0]
  const lastPeriod = document.periods[document.periods.length - 1]
  const lastPoint = series?.points[series.points.length - 1]
  return Boolean(
    lastPeriod &&
      lastPoint &&
      lastPoint.status === 'ok' &&
      lastPeriod.endDate < document.context.effectiveDate,
  )
}
