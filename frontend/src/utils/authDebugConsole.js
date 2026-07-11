/**
 * Console debugging interface for authentication
 * Makes AuthDebugger available in browser console
 */
import authDebug from './authDebug'

// Make debugger available in console for easy testing
if (typeof window !== 'undefined') {
  window.authDebug = authDebug

  // Add convenience methods to console
  console.log('🔧 Authentication debugger loaded. Available commands:')
  console.log(
    '  authDebug.runFullDiagnostic() - Run complete authentication check'
  )
  console.log('  authDebug.checkTokenStorage() - Check localStorage tokens')
  console.log(
    '  authDebug.checkStoreAuthentication() - Check Vuex store auth state'
  )
  console.log(
    '  authDebug.checkTokenExpiration() - Check token expiration times'
  )
  console.log(
    '  authDebug.monitorApiRequests() - Monitor API requests for auth headers'
  )
}

export default authDebug
