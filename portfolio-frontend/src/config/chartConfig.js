import { nextTick } from 'vue'

const getFontFamily = () => getComputedStyle(document.documentElement).getPropertyValue('--system-font').trim();

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
    pieChartOptions: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false, // Hide the legend
        },
        tooltip: {
          enabled: false, // Disable tooltips as we'll use data labels
        },
        datalabels: {
          color: '#000000', // Use black for better visibility outside the chart
          font: {
            family: fontFamily,
            size: 14,
          },
          formatter: (value, ctx) => {
            let sum = 0;
            let dataArr = ctx.chart.data.datasets[0].data;
            dataArr.map(data => {
              sum += data;
            });
            let percentage = (value * 100 / sum).toFixed(0) + "%";
            return ctx.chart.data.labels[ctx.dataIndex] + ' ' + percentage;
          },
          anchor: 'end',
          align: 'end',
          offset: 8, // Move labels slightly away from the pie
        },
      },
      layout: {
        padding: {
          top: 50,
          bottom: 50,
          left: 50, // Increase left padding to make room for labels
          right: 50, // Increase right padding to make room for labels
        },
      },
    },
    navChartOptions: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: {
            display: false
          },
          ticks: {
            font: axisFont
          }
        },
        y: {
          grace: '5%',
          stacked: true,
          title: {
            display: true,
            text: currency,
            font: axisFont
          },
          grid: {
            display: false
          },
          ticks: {
            font: axisFont
          }
        },
        y1: {
          grace: '5%',
          type: 'linear',
          display: true,
          position: 'right',
          ticks: {
            callback: value => (value * 100).toFixed(0) + '%',
            font: axisFont
          },
          grid: {
            display: false
          }
        }
      },
      plugins: {
        datalabels: {
          anchor: (context) => {
            const datasets = context.chart.data.datasets.filter(ds => ds.type === 'bar')
            const dataIndex = context.dataIndex
            const sum = datasets.reduce((total, ds) => total + (ds.data[dataIndex] || 0), 0)
            const lastNegativeIndex = datasets.map(ds => ds.data[dataIndex] || 0).findLastIndex(v => v < 0)
            return sum >= 0 ? 'end' : (lastNegativeIndex !== -1 ? 'start' : 'end')
          },
          align: (context) => {
            const datasets = context.chart.data.datasets.filter(ds => ds.type === 'bar')
            const dataIndex = context.dataIndex
            const sum = datasets.reduce((total, ds) => total + (ds.data[dataIndex] || 0), 0)
            const lastPositiveIndex = datasets.map(ds => ds.data[dataIndex] || 0).findLastIndex(v => v > 0)
            return sum >= 0 ? (lastPositiveIndex !== -1 ? 'top' : 'bottom') : 'bottom'
          },
          font: {
            family: fontFamily,
            size: 14,
          },
          formatter: (value, context) => {
            if (context.dataset.type === 'line') {
              return (value * 100).toFixed(1) + '%'
            }
            
            const datasets = context.chart.data.datasets.filter(ds => ds.type === 'bar')
            const dataIndex = context.dataIndex
            
            const sum = datasets.reduce((total, ds) => total + (ds.data[dataIndex] || 0), 0)
            
            const labelIndex = sum >= 0 
              ? datasets.map(ds => ds.data[dataIndex] || 0).findLastIndex(v => v > 0)
              : datasets.map(ds => ds.data[dataIndex] || 0).findLastIndex(v => v < 0)
            
            return context.datasetIndex === labelIndex ? sum.toFixed(1) : null
          },
          color: () => 'black', // Use black for all labels
          offset: (context) => {
            const datasets = context.chart.data.datasets.filter(ds => ds.type === 'bar')
            const dataIndex = context.dataIndex
            const sum = datasets.reduce((total, ds) => total + (ds.data[dataIndex] || 0), 0)
            const lastPositiveIndex = datasets.map(ds => ds.data[dataIndex] || 0).findLastIndex(v => v > 0)
            return sum >= 0 ? (lastPositiveIndex !== -1 ? 5 : -5) : -5
          },
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              let value = context.parsed.y;

              if (label === "IRR (RHS)" || label === "Rolling IRR (RHS)") {
                // For line charts (IRR), show percentage with one decimal point
                return `${label}: ${(value * 100).toFixed(1)}%`;
              } else {
                // For bar charts (NAV and other categories), show number with one decimal point
                return `${label}: ${value.toFixed(1)}`;
              }
            }
          }
        },
      }
    },
    colorPalette: [
      '#1976D2', // primary (blue)
      '#4CAF50', // success (green)
      '#FF9800', // warning (orange)
      '#F44336', // error (red)
      '#9C27B0', // purple
      '#00BCD4', // cyan
      '#795548', // brown
      '#607D8B', // blue-grey
      '#E91E63', // pink
      '#3F51B5', // indigo
      '#009688', // teal
      '#FFC107', // amber
    ]
  }
}