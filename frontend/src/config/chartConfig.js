import { nextTick } from 'vue'
import { palette } from '@/theme'

const getFontFamily = () =>
  getComputedStyle(document.documentElement)
    .getPropertyValue('--system-font')
    .trim()

export const colorPalette = [
  palette.primary, // #0F4C81
  palette.secondary, // #5C6B7A
  palette.success, // #1E7F4F
  palette.warning, // #9A6700
  palette.info, // #0B5FA5
  '#7A4E2D',
  '#607D8B',
  '#8E4585',
  '#00838F',
  palette.error, // #B3261E
  '#6D4C41',
  '#9E9D24',
]

export const getChartOptions = async (currency) => {
  await nextTick()
  const fontFamily = getFontFamily()

  const axisFont = {
    family: fontFamily,
    size: 12,
  }

  return {
    // chartOptions: {
    //   responsive: false,
    //   maintainAspectRatio: false,
    //   plugins: {
    //     legend: {
    //       position: 'top',
    //       labels: {
    //         font: {
    //           family: fontFamily,
    //         },
    //       },
    //     },
    //     title: {
    //       display: true,
    //       text: 'Chart.js Line Chart',
    //       font: {
    //         family: fontFamily,
    //       },
    //     },
    //   },
    // },
    barChartOptions: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      scales: {
        x: { ticks: { font: axisFont } },
        y: { grid: { display: false }, ticks: { font: axisFont } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: true },
        datalabels: {
          anchor: 'end',
          align: 'end',
          offset: 4,
          color: '#1A1C1E',
          font: { family: fontFamily, size: 12 },
          formatter: (value, ctx) => {
            const data = ctx.chart.data.datasets[0].data
            const sum = data.reduce((a, b) => a + b, 0) || 1
            return `${(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} (${((value * 100) / sum).toFixed(1)}%)`
          },
        },
      },
      layout: { padding: { right: 80 } },
    },
    navChartOptions: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: {
            display: false,
          },
          ticks: {
            font: axisFont,
          },
        },
        y: {
          grace: '5%',
          stacked: true,
          title: {
            display: true,
            text: currency,
            font: axisFont,
          },
          grid: {
            display: false,
          },
          ticks: {
            font: axisFont,
          },
        },
        y1: {
          grace: '5%',
          type: 'linear',
          display: true,
          position: 'right',
          ticks: {
            callback: (value) => (value * 100).toFixed(0) + '%',
            font: axisFont,
          },
          grid: {
            display: false,
          },
        },
      },
      plugins: {
        datalabels: {
          anchor: (context) => {
            const datasets = context.chart.data.datasets.filter(
              (ds) => ds.type === 'bar'
            )
            const dataIndex = context.dataIndex
            const sum = datasets.reduce(
              (total, ds) => total + (ds.data[dataIndex] || 0),
              0
            )
            const lastNegativeIndex = datasets
              .map((ds) => ds.data[dataIndex] || 0)
              .findLastIndex((v) => v < 0)
            return sum >= 0 ? 'end' : lastNegativeIndex !== -1 ? 'start' : 'end'
          },
          align: (context) => {
            const datasets = context.chart.data.datasets.filter(
              (ds) => ds.type === 'bar'
            )
            const dataIndex = context.dataIndex
            const sum = datasets.reduce(
              (total, ds) => total + (ds.data[dataIndex] || 0),
              0
            )
            const lastPositiveIndex = datasets
              .map((ds) => ds.data[dataIndex] || 0)
              .findLastIndex((v) => v > 0)
            return sum >= 0
              ? lastPositiveIndex !== -1
                ? 'top'
                : 'bottom'
              : 'bottom'
          },
          font: {
            family: fontFamily,
            size: 14,
          },
          formatter: (value, context) => {
            if (context.dataset.type === 'line') {
              return (value * 100).toFixed(1) + '%'
            }

            const datasets = context.chart.data.datasets.filter(
              (ds) => ds.type === 'bar'
            )
            const dataIndex = context.dataIndex

            const sum = datasets.reduce(
              (total, ds) => total + (ds.data[dataIndex] || 0),
              0
            )

            const labelIndex =
              sum >= 0
                ? datasets
                    .map((ds) => ds.data[dataIndex] || 0)
                    .findLastIndex((v) => v > 0)
                : datasets
                    .map((ds) => ds.data[dataIndex] || 0)
                    .findLastIndex((v) => v < 0)

            return context.datasetIndex === labelIndex ? sum.toFixed(1) : null
          },
          color: () => '#1A1C1E',
          offset: (context) => {
            const datasets = context.chart.data.datasets.filter(
              (ds) => ds.type === 'bar'
            )
            const dataIndex = context.dataIndex
            const sum = datasets.reduce(
              (total, ds) => total + (ds.data[dataIndex] || 0),
              0
            )
            const lastPositiveIndex = datasets
              .map((ds) => ds.data[dataIndex] || 0)
              .findLastIndex((v) => v > 0)
            return sum >= 0 ? (lastPositiveIndex !== -1 ? 5 : -5) : -5
          },
        },
        tooltip: {
          callbacks: {
            label: function (context) {
              let label = context.dataset.label || ''
              let value = context.parsed.y

              if (label === 'IRR (RHS)' || label === 'Rolling IRR (RHS)') {
                // For line charts (IRR), show percentage with one decimal point
                return `${label}: ${(value * 100).toFixed(1)}%`
              } else {
                // For bar charts (NAV and other categories), show number with one decimal point
                return `${label}: ${value.toFixed(1)}`
              }
            },
          },
        },
      },
    },
  }
}
