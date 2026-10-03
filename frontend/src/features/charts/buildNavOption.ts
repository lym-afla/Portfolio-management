// Pure ECharts option construction for the NAV pilot (C3). Type-only import:
// no ECharts runtime code enters this module's graph — the lazy EChartsNav
// component owns the runtime. Money bars stack on axis 0; both raw-ratio IRRs
// run on axis 1 unstacked with connectNulls false so missing returns stay
// gaps. Series identity, roles, axes and labels come from the server
// document; hidden series are excluded rather than merged away; the zoom
// window is view-only state and never alters data.
//
// Presentation-only formatting (axis names and the tooltip) still derives
// exclusively from server strings: tooltips show exact displays with status/
// reason/knownSubtotal (never plotted numbers), and every server string is
// HTML-escaped because ECharts renders tooltip strings as markup.
import type { EChartsOption } from 'echarts'
import type { ChartDocument, ChartSeries, ChartUnit, ChartValue } from './contracts'
import { toPlotNumber } from './renderBoundary'
import { irrLineStyle, seriesColor } from './seriesStyles'
import type { ChartInteraction } from './interaction'

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function unitLabel(unit: ChartUnit): string {
  if (unit.kind === 'money') {
    return unit.plotDivisor === '1000' ? `${unit.currency} thousands` : unit.currency
  }
  if (unit.kind === 'ratio') return '%'
  if (unit.kind === 'percent_of_nominal') return '% of nominal'
  return 'quantity'
}

function valueLine(point: ChartValue | undefined): string {
  if (!point) return '–'
  if (point.status === 'ok') return point.display
  const subtotal = 'knownSubtotal' in point ? `; known subtotal ${point.knownSubtotal}` : ''
  return `${point.display} — ${point.status} (${point.reason})${subtotal}`
}

interface TooltipParam {
  axisValue?: string
  seriesId?: string
}

export function buildNavOption(document: ChartDocument, interaction: ChartInteraction): EChartsOption {
  const labelsByKey = new Map(document.periods.map((period) => [period.key, period.displayLabel]))
  const seriesById = new Map(document.series.map((series) => [series.id, series]))
  const visible = new Set(interaction.visibleSeriesIds)
  const series: NonNullable<EChartsOption['series']> = document.series
    .filter((entry) => visible.has(entry.id))
    .map((entry) => navSeriesOption(entry))
  const periodCount = document.periods.length
  let startValue = 0
  let endValue = 100
  if (interaction.viewport && periodCount > 0) {
    const keys = document.periods.map((period) => period.key)
    const first = keys.indexOf(interaction.viewport.firstPeriodKey)
    const last = keys.indexOf(interaction.viewport.lastPeriodKey)
    if (first >= 0 && last >= 0 && first <= last) {
      startValue = (first / Math.max(1, periodCount - 1)) * 100
      endValue = (last / Math.max(1, periodCount - 1)) * 100
    }
  }
  const moneyUnit = document.series.find((entry) => entry.axis === 'money')?.unit
  const moneyAxisName = moneyUnit ? unitLabel(moneyUnit) : undefined
  return {
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => navTooltip(document, seriesById, params),
    },
    xAxis: [{
      type: 'category',
      data: document.periods.map((period) => period.key),
      axisLabel: { formatter: (value: string) => labelsByKey.get(value) ?? value },
    }],
    yAxis: [
      moneyAxisName ? { type: 'value', name: moneyAxisName } : { type: 'value' },
      { type: 'value', scale: true, name: '%' },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, startValue: interaction.viewport ? undefined : 0, endValue: interaction.viewport ? undefined : 100, start: startValue, end: endValue },
      { type: 'slider', xAxisIndex: 0, start: startValue, end: endValue },
    ],
    series,
  }
}

/** Exact server displays by period key — markup-escaped for ECharts. */
function navTooltip(
  document: ChartDocument,
  seriesById: ReadonlyMap<string, ChartSeries>,
  params: unknown,
): string {
  const list = Array.isArray(params) ? (params as TooltipParam[]) : [params as TooltipParam]
  const key = list[0]?.axisValue
  const period = document.periods.find((entry) => entry.key === key)
  if (!period) return ''
  const index = document.periods.indexOf(period)
  const lines = [`<strong>${escapeHtml(period.displayLabel)} (${escapeHtml(period.endDate)})</strong>`]
  for (const param of list) {
    const series = param?.seriesId ? seriesById.get(param.seriesId) : undefined
    if (!series) continue
    lines.push(
      `${escapeHtml(series.label)}: ${escapeHtml(valueLine(series.points[index]))} <em>(${escapeHtml(unitLabel(series.unit))})</em>`,
    )
  }
  const total = document.totals?.[index]
  if (total) {
    lines.push(`Portfolio NAV (all categories): ${escapeHtml(valueLine(total))}`)
  }
  return lines.join('<br/>')
}

function navSeriesOption(series: ChartSeries): Record<string, unknown> {
  const isIrr = series.metric === 'irr_inception' || series.metric === 'irr_interval'
  const option: Record<string, unknown> = {
    id: series.id,
    name: series.label,
    type: series.role,
    yAxisIndex: series.axis === 'return' ? 1 : 0,
    connectNulls: false,
    smooth: false,
    data: series.points.map(toPlotNumber),
  }
  if (series.role === 'bar') {
    option.stack = 'nav'
    option.itemStyle = { color: seriesColor(series.id) }
  } else {
    option.itemStyle = { color: seriesColor(series.id) }
    option.lineStyle = isIrr ? { ...irrLineStyle(series.id), color: seriesColor(series.id) } : { color: seriesColor(series.id) }
  }
  return option
}
