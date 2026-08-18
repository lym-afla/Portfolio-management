// src/theme.js
// Single source of truth for the app's visual identity.
export const palette = {
  primary: '#0F4C81', // deep brokerage blue — anchors the app
  secondary: '#5C6B7A', // slate for secondary text/accents
  background: '#F7F8FA',
  surface: '#FFFFFF',
  success: '#1E7F4F',
  error: '#B3261E',
  info: '#0B5FA5',
  warning: '#9A6700',
}

export function createAppTheme() {
  return {
    defaultTheme: 'light',
    themes: {
      light: {
        dark: false,
        colors: { ...palette },
        variables: {
          fontFamily: 'var(--system-font)',
          'border-color': '#E2E6EB',
        },
      },
    },
  }
}
