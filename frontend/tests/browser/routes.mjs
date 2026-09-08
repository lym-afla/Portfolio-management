export const routes = [
  { path: '/', authenticated: true, expectedPath: '/dashboard' },
  { path: '/login', authenticated: false },
  { path: '/register', authenticated: false },
  { path: '/dashboard', authenticated: true },
  { path: '/open-positions', authenticated: true },
  { path: '/closed-positions', authenticated: true },
  { path: '/transactions', authenticated: true },
  { path: '/profile', authenticated: true },
  { path: '/profile/edit', authenticated: true },
  { path: '/profile/settings', authenticated: true },
  { path: '/database', authenticated: true },
  { path: '/database/brokers', authenticated: true },
  { path: '/database/accounts', authenticated: true },
  { path: '/database/prices', authenticated: true },
  { path: '/database/securities', authenticated: true },
  { path: '/database/securities/1', authenticated: true },
  { path: '/database/fx', authenticated: true },
  { path: '/summary', authenticated: true },
]

export const viewports = [
  { name: 'desktop', width: 1440, height: 1000, zoom: 1 },
  { name: 'tablet', width: 1024, height: 768, zoom: 1 },
  { name: 'mobile', width: 390, height: 844, zoom: 1 },
  { name: 'zoom-200', width: 1440, height: 1000, zoom: 2 },
]
