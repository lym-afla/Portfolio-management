/**
 * Logger utility that only outputs logs in development or testing environments
 * Replaces direct console.log usage throughout the application
 */

// Check if we're in production environment
const isProduction = process.env.NODE_ENV === 'production'

// Allow override for testing in non-production environments
let debugEnabled = !isProduction

// Color codes for different log types
const COLORS = {
  log: '#3498db',     // Blue
  info: '#2ecc71',    // Green
  warn: '#f39c12',    // Orange
  error: '#e74c3c',   // Red
  debug: '#9b59b6',   // Purple
}

/**
 * Create console message with timestamp, category and formatted content
 */
const createMessage = (category, args) => {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, -1)
  const prefix = `[${timestamp}][${category}]`
  return [
    `%c${prefix}`,
    `color: ${COLORS[category] || COLORS.log}; font-weight: bold;`,
    ...args
  ]
}

/**
 * Main logger object with methods for each log level
 */
const logger = {
  /**
   * Enable or disable all logging (overrides production settings for testing)
   */
  setDebugEnabled(enabled) {
    debugEnabled = enabled
    console.log(...createMessage('log', [`[Logger]`, `Logging ${enabled ? 'enabled' : 'disabled'}`]))
  },

  /**
   * Get current debug status
   */
  isDebugEnabled() {
    return debugEnabled
  },
  
  /**
   * Standard log
   */
  log(module, ...args) {
    if (isProduction && !debugEnabled) return
    console.log(...createMessage('log', [`[${module}]`, ...args]))
  },
  
  /**
   * Info level (for important information)
   */
  info(module, ...args) {
    if (isProduction && !debugEnabled) return
    console.info(...createMessage('info', [`[${module}]`, ...args]))
  },
  
  /**
   * Warning level
   */
  warn(module, ...args) {
    if (isProduction && !debugEnabled) return
    console.warn(...createMessage('warn', [`[${module}]`, ...args]))
  },
  
  /**
   * Error level (always logs, even in production)
   */
  error(module, ...args) {
    // Errors should be logged even in production for monitoring
    console.error(...createMessage('error', [`[${module}]`, ...args]))
  },
  
  /**
   * Debug level (most verbose, for detailed debugging)
   */
  debug(module, ...args) {
    if (isProduction && !debugEnabled) return
    console.debug(...createMessage('debug', [`[${module}]`, ...args]))
  },
  
  /**
   * Group logs together (for better organization)
   */
  group(title) {
    if (isProduction && !debugEnabled) return
    console.group(title)
  },
  
  /**
   * End group
   */
  groupEnd() {
    if (isProduction && !debugEnabled) return
    console.groupEnd()
  },
  
  /**
   * Log execution time of a function
   */
  time(module, label) {
    if (isProduction && !debugEnabled) return
    console.time(`[${module}] ${label}`)
  },
  
  /**
   * End timing
   */
  timeEnd(module, label) {
    if (isProduction && !debugEnabled) return
    console.timeEnd(`[${module}] ${label}`)
  }
}

// Export the logger as default
export default logger 