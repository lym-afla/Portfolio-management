export const chartOptions = {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Chart.js Line Chart',
      },
    },
  }
  
  export const pieChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'right',
      },
    },
  }
  
  // Vuetify 3 inspired color palette
  export const colorPalette = [
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