import { nextTick } from 'vue'

const getFontFamily = () => getComputedStyle(document.documentElement).getPropertyValue('--system-font').trim();

export const getChartOptions = async () => {
  await nextTick()
  const fontFamily = getFontFamily()

  return {
    chartOptions: {
      responsive: false,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: {
              family: fontFamily,
            },
          },
        },
        title: {
          display: true,
          text: 'Chart.js Line Chart',
          font: {
            family: fontFamily,
          },
        },
      },
    },
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