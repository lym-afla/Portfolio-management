export const mockDashboardData = {
  summary: {
    NAV: '$1,000,000',
    Invested: '+5.2%',
    'Cash-out': '+3.8%',
    IRR: '+3.8%',
    Return: '+38.2%',
  },
  assetTypeData: {
    Stocks: { amount: 500000 },
    Bonds: { amount: 300000 },
    Cash: { amount: 200000 },
  },
  assetClassData: {
    Equities: { amount: 600000 },
    'Fixed Income': { amount: 300000 },
    Alternatives: { amount: 100000 },
  },
  currencyData: {
    USD: { amount: 700000 },
    EUR: { amount: 200000 },
    GBP: { amount: 100000 },
  },
  summaryOverTimeData: {
    lines: [
      {
        name: 'BoP NAV',
        values: {
          2020: 900000,
          2021: 950000,
          2022: 980000,
          '2023YTD': 1000000,
          'All-time': 1000000,
        },
      },
      {
        name: 'Contributions',
        values: {
          2020: 50000,
          2021: 30000,
          2022: 20000,
          '2023YTD': 10000,
          'All-time': 110000,
        },
      },
      {
        name: 'Withdrawals',
        values: {
          2020: -10000,
          2021: -5000,
          2022: -15000,
          '2023YTD': -5000,
          'All-time': -35000,
        },
      },
      {
        name: 'Investment Return',
        values: {
          2020: 10000,
          2021: 5000,
          2022: 15000,
          '2023YTD': 15000,
          'All-time': 45000,
        },
      },
      {
        name: 'EoP NAV',
        values: {
          2020: 950000,
          2021: 980000,
          2022: 1000000,
          '2023YTD': 1020000,
          'All-time': 1020000,
        },
      },
      {
        name: 'TSR',
        values: {
          2020: '5.2%',
          2021: '2.6%',
          2022: '3.8%',
          '2023YTD': '3.0%',
          'All-time': '15.2%',
        },
      },
    ],
    years: ['2020', '2021', '2022'],
    currentYear: '2023',
  },
  navChartData: {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'NAV',
        data: [95, 96, 98, 99, 100, 102],
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
      },
    ],
  },
}
