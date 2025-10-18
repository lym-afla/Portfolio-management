# Frontend Authentication Debugging Guide

## Overview
This guide helps you debug frontend authentication issues that may be causing the session persistence problem with effective dates.

## 🔧 Debugging Tools Available

### 1. Browser Console Commands
Open your browser's developer console (F12) and use these commands:

```javascript
// Run complete authentication diagnostic
authDebug.runFullDiagnostic()

// Check individual components
authDebug.checkTokenStorage()
authDebug.checkStoreAuthentication()
authDebug.checkTokenExpiration()

// Monitor API requests for missing auth headers
authDebug.monitorApiRequests()
```

### 2. Visual Debug Panel
Navigate to `/debug-auth` (only available in development) to access the visual debugging panel with buttons to:
- Run full diagnostic
- Check token storage
- Verify store authentication
- Test token expiration
- Make test API calls

### 3. Enhanced Logging
Check the browser console for enhanced authentication logging:
- 🔒 401 Unauthorized errors
- 🔄 Token refresh attempts
- ✅ Successful operations
- ❌ Failed operations

## 🚀 Quick Debugging Steps

### Step 1: Check Authentication Status
```javascript
// In browser console
authDebug.runFullDiagnostic()
```

Look for:
- ✅ Authentication Healthy - Everything is working
- ❌ Authentication Issues - Problems detected

### Step 2: Identify Common Issues

#### Issue: No Access Token
**Symptoms**: `No access token in localStorage`
**Solution**: User needs to log in again

#### Issue: Expired Token
**Symptoms**: `Access token is expired`
**Solution**: Token refresh should happen automatically, but may need re-login

#### Issue: No User Data in Store
**Symptoms**: `Authenticated but no user data in store`
**Solution**: Refresh the page or re-login

#### Issue: API Requests Without Auth
**Symptoms**: `API request without auth header` warnings
**Solution**: Check token storage and re-authenticate

### Step 3: Test the Settings Dialog
1. Navigate to any page (e.g., Dashboard)
2. Click the settings gear icon
3. Change the date and click Update
4. Check console for authentication debugging messages
5. Verify the date persists across page refreshes

## 📊 What to Look For

### Healthy Authentication State:
- ✅ Access token exists and is valid JWT format
- ✅ Refresh token exists and is not expired
- ✅ Vuex store shows `isAuthenticated: true`
- ✅ User data is present in store
- ✅ API calls include Authorization header
- ✅ Settings updates work and persist

### Problematic Authentication State:
- ❌ No tokens in localStorage
- ❌ Expired tokens that didn't refresh
- ❌ Store shows `isAuthenticated: false`
- ❌ Missing user data in store
- ❌ API calls return 401 Unauthorized
- ❌ Settings updates fail or don't persist

## 🔍 Specific Session Persistence Debugging

### To debug the effective date session issue:

1. **Check Current State**:
   ```javascript
   // Check what date is currently set
   console.log('Current effective date:', store.state.effectiveCurrentDate)

   // Check backend session
   authDebug.runFullDiagnostic()
   ```

2. **Test Settings Update**:
   - Open settings dialog (gear icon)
   - Change the date to something obvious (e.g., 2021-01-01)
   - Click Update
   - Check console for authentication messages
   - Refresh the page and see if date persists

3. **Check API Authentication**:
   ```javascript
   // Monitor API requests
   authDebug.monitorApiRequests()

   // Then trigger a settings update and watch for auth issues
   ```

## 🛠️ Common Fixes

### Fix 1: Re-authenticate
If tokens are missing or expired:
1. Log out
2. Clear browser localStorage
3. Log back in

### Fix 2: Token Refresh Issues
If token refresh is failing:
1. Check network connectivity
2. Verify refresh token endpoint is working
3. Check for CORS issues

### Fix 3: Store Initialization
If store is not properly initialized:
1. Refresh the page
2. Check router navigation logs
3. Verify user data fetching

## 📝 Reporting Issues

When reporting authentication issues, please provide:
1. Output of `authDebug.runFullDiagnostic()`
2. Browser console errors/warnings
3. Network tab screenshots showing failed requests
4. Steps to reproduce the problem

## 🎯 Expected Outcome

After debugging, you should see:
- All API calls properly authenticated with Bearer tokens
- Settings updates working correctly
- Effective date persisting across page refreshes
- No 401 Unauthorized errors
