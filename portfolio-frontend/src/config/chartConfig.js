import { nextTick } from 'vue'

const getFontFamily = () => getComputedStyle(document.documentElement).getPropertyValue('--system-font').trim();

export const getChartOptions = async (currency) => {
  await nextTick()
  const fontFamily = getFontFamily()

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
      aspectRatio: 1.3,
      scales: {
        x: {
          stacked: true,
          grid: {
            display: false
          }
        },
        y: {
          grace: '5%',
          stacked: true,
          title: {
            display: true,
            text: currency,
          },
          grid: {
            display: false
          }
        },
        y1: {
          grace: '5%',
          type: 'linear',
          display: true,
          position: 'right',
          ticks: {
            callback: value => (value * 100).toFixed(0) + '%'
          },
          grid: {
            display: false
          }
        }
      },
      plugins: {
        datalabels: {
          anchor: "end",
          align: "top",
          formatter: (value, context) => {
            if (context.dataset.label === "Rolling IRR (RHS)" || context.dataset.label === "IRR (RHS)") {
              return (value * 100).toFixed(0) + '%';
            }
            
            const dataArray = context.chart.data.datasets
              .filter(dataset => !["IRR (RHS)", "Rolling IRR (RHS)"].includes(dataset.label))
              .map(dataset => parseFloat(dataset.data[context.dataIndex] || 0));

            const sum = Math.round(dataArray.reduce((a, b) => a + b, 0) * 10) / 10;
            const labelIndex = dataArray.findLastIndex(value => value > 0);

            return context.datasetIndex === labelIndex + 1 ? sum.toLocaleString().replace(/,/g, '.') : "";
          },
        },
        tooltip: {
          callbacks: {
            label: function(tooltipItem) {
              if (tooltipItem.datasetIndex > 1) {
                return Math.round(tooltipItem.raw * 10) / 10;
              } else {
                return (tooltipItem.raw * 100).toFixed(1) + '%';
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