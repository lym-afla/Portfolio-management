// Pure ECharts option construction for the NAV pilot (C3). Type-only import:
// no ECharts runtime code enters this module's graph — the lazy EChartsNav
// component owns the runtime. Money bars stack on axis 0; both raw-ratio IRRs
// run on axis 1 unstacked with connectNulls false so missing returns stay
// gaps. Series identity, roles, axes and labels come from the server
// document; hidden series are excluded rather than merged away; the zoom
// window is view-only state and never alters data.
import type { EChartsOption } from 'echarts'
import type { ChartDocument, ChartSeries } from './contracts'
import { toPlotNumber } from './renderBoundary'
import { irrLineStyle, seriesColor } from './seriesStyles'
import type { ChartInteraction } from './interaction'

export function buildNavOption(document: ChartDocument, interaction: ChartInteraction): EChartsOption {
  const labelsByKey = new Map(document.periods.map((period) => [period.key, period.displayLabel]))
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
  return {
    aria: { enabled: true },
    animation: false,
    tooltip: { trigger: 'axis' },
    xAxis: [{
      type: 'category',
      data: document.periods.map((period) => period.key),
      axisLabel: { formatter: (value: string) => labelsByKey.get(value) ?? value },
    }],
    yAxis: [
      { type: 'value' },
      { type: 'value', scale: true },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, startValue: interaction.viewport ? undefined : 0, endValue: interaction.viewport ? undefined : 100, start: startValue, end: endValue },
      { type: 'slider', xAxisIndex: 0, start: startValue, end: endValue },
    ],
    series,
  }
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
