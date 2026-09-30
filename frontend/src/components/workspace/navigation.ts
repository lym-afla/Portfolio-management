export const workspaceNavigation: ReadonlyArray<{
  label: string
  to: string
  icon: string
  section: 'portfolio' | 'data' | 'personal'
}> = [
  {
    label: 'Overview',
    to: '/dashboard',
    icon: 'mdi-monitor-dashboard',
    section: 'portfolio',
  },
  {
    label: 'Performance',
    to: '/summary',
    icon: 'mdi-apps',
    section: 'portfolio',
  },
  {
    label: 'Open positions',
    to: '/open-positions',
    icon: 'mdi-clipboard-check',
    section: 'portfolio',
  },
  {
    label: 'Closed positions',
    to: '/closed-positions',
    icon: 'mdi-clipboard-remove',
    section: 'portfolio',
  },
  {
    label: 'Transactions',
    to: '/transactions',
    icon: 'mdi-swap-horizontal',
    section: 'portfolio',
  },
  {
    label: 'Brokers',
    to: '/database/brokers',
    icon: 'mdi-office-building',
    section: 'data',
  },
  {
    label: 'Accounts',
    to: '/database/accounts',
    icon: 'mdi-bank',
    section: 'data',
  },
  {
    label: 'Prices',
    to: '/database/prices',
    icon: 'mdi-file-document-outline',
    section: 'data',
  },
  {
    label: 'Securities',
    to: '/database/securities',
    icon: 'mdi-chart-line',
    section: 'data',
  },
  {
    label: 'FX',
    to: '/database/fx',
    icon: 'mdi-currency-usd',
    section: 'data',
  },
  {
    label: 'Profile',
    to: '/profile',
    icon: 'mdi-account-circle',
    section: 'personal',
  },
]
