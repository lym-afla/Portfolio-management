// WCAG 2.2.1 (Timing): error messages must persist until dismissed so users
// have enough time to read them. Success/info snackbars auto-hide quickly.
export type SnackbarSeverity = 'error' | 'success' | 'info' | 'warning'

export function snackbarTimeout(severity: SnackbarSeverity): number {
  return severity === 'error' ? -1 : 5000
}
