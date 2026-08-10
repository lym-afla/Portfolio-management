/**
 * Logger utility that only outputs logs in development or testing environments
 * Replaces direct console.log usage throughout the application
 */

type LogLevel = 'log' | 'info' | 'warn' | 'error' | 'debug'

// Check if we're in production environment
const isProduction = import.meta.env.PROD

// Allow override for testing in non-production environments
let debugEnabled = !isProduction

// Color codes for different log types
const COLORS: Record<LogLevel, string> = {
  log: '#3498db', // Blue
  info: '#2ecc71', // Green
  warn: '#f39c12', // Orange
  error: '#e74c3c', // Red
  debug: '#9b59b6', // Purple
}

/**
 * Create console message with timestamp, category and formatted content
 */
const createMessage = (category: LogLevel, args: unknown[]) => {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, -1)
  const prefix = `[${timestamp}][${category}]`
  return [
    `%c${prefix}`,
    `color: ${COLORS[category] || COLORS.log}; font-weight: bold;`,
    ...args,
  ]
}

export interface Logger {
  setDebugEnabled(enabled: boolean): void
  isDebugEnabled(): boolean
  log(module: string, ...args: unknown[]): void
  info(module: string, ...args: unknown[]): void
  warn(module: string, ...args: unknown[]): void
  error(module: string, ...args: unknown[]): void
  debug(module: string, ...args: unknown[]): void
  group(title: string): void
  groupEnd(): void
  time(module: string, label: string): void
  timeEnd(module: string, label: string): void
}

/**
 * Main logger object with methods for each log level
 */
const logger: Logger = {
  setDebugEnabled(enabled: boolean) {
    debugEnabled = enabled
    console.log(
      ...createMessage('log', [
        `[Logger]`,
        `Logging ${enabled ? 'enabled' : 'disabled'}`,
      ])
    )
  },

  isDebugEnabled() {
    return debugEnabled
  },

  log(module: string, ...args: unknown[]) {
    if (isProduction && !debugEnabled) return
    console.log(...createMessage('log', [`[${module}]`, ...args]))
  },

  info(module: string, ...args: unknown[]) {
    if (isProduction && !debugEnabled) return
    console.info(...createMessage('info', [`[${module}]`, ...args]))
  },

  warn(module: string, ...args: unknown[]) {
    if (isProduction && !debugEnabled) return
    console.warn(...createMessage('warn', [`[${module}]`, ...args]))
  },

  error(module: string, ...args: unknown[]) {
    console.error(...createMessage('error', [`[${module}]`, ...args]))
  },

  debug(module: string, ...args: unknown[]) {
    if (isProduction && !debugEnabled) return
    console.debug(...createMessage('debug', [`[${module}]`, ...args]))
  },

  group(title: string) {
    if (isProduction && !debugEnabled) return
    console.group(title)
  },

  groupEnd() {
    if (isProduction && !debugEnabled) return
    console.groupEnd()
  },

  time(module: string, label: string) {
    if (isProduction && !debugEnabled) return
    console.time(`[${module}] ${label}`)
  },

  timeEnd(module: string, label: string) {
    if (isProduction && !debugEnabled) return
    console.timeEnd(`[${module}] ${label}`)
  },
}

export default logger
