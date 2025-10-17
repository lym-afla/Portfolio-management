<template>
  <v-card class="auth-debug-panel" max-width="800">
    <v-card-title class="text-h6"> 🔐 Authentication Debug Panel </v-card-title>

    <v-card-text>
      <v-alert
        v-if="diagnosticResults"
        :type="diagnosticResults.assessment.isHealthy ? 'success' : 'error'"
        class="mb-4"
      >
        <div class="text-h6">
          {{
            diagnosticResults.assessment.isHealthy
              ? '✅ Authentication Healthy'
              : '❌ Authentication Issues'
          }}
        </div>
        <div v-if="!diagnosticResults.assessment.isHealthy">
          <strong>Issues:</strong>
          <ul>
            <li
              v-for="issue in diagnosticResults.assessment.issues"
              :key="issue"
            >
              {{ issue }}
            </li>
          </ul>
          <div class="mt-2">
            <strong>Recommendation:</strong>
            {{ diagnosticResults.assessment.recommendation }}
          </div>
        </div>
      </v-alert>

      <v-row>
        <v-col cols="12">
          <v-btn
            color="primary"
            @click="runDiagnostic"
            :loading="isRunningDiagnostic"
            block
          >
            🔍 Run Full Authentication Diagnostic
          </v-btn>
        </v-col>

        <v-col cols="12">
          <v-btn
            color="warning"
            @click="fixCorruptedTokens"
            :loading="isLoading"
            block
          >
            🛠️ Fix Corrupted Tokens
          </v-btn>
        </v-col>

        <v-col cols="12" md="6">
          <v-btn
            variant="outlined"
            @click="checkTokenStorage"
            :loading="isLoading"
            block
          >
            📋 Check Token Storage
          </v-btn>
        </v-col>

        <v-col cols="12" md="6">
          <v-btn
            variant="outlined"
            @click="checkStoreAuth"
            :loading="isLoading"
            block
          >
            🏪 Check Store Auth
          </v-btn>
        </v-col>

        <v-col cols="12" md="6">
          <v-btn
            variant="outlined"
            @click="checkTokenExpiration"
            :loading="isLoading"
            block
          >
            ⏰ Check Token Expiration
          </v-btn>
        </v-col>

        <v-col cols="12" md="6">
          <v-btn
            variant="outlined"
            @click="testApiCall"
            :loading="isLoading"
            block
          >
            🌐 Test API Call
          </v-btn>
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <div v-if="results">
        <v-expansion-panels>
          <v-expansion-panel v-if="results.tokenStorage">
            <v-expansion-panel-title>
              📋 Token Storage Details
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre>{{ JSON.stringify(results.tokenStorage, null, 2) }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel v-if="results.storeAuth">
            <v-expansion-panel-title>
              🏪 Store Authentication Details
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre>{{ JSON.stringify(results.storeAuth, null, 2) }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel v-if="results.tokenExpiration">
            <v-expansion-panel-title>
              ⏰ Token Expiration Details
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre>{{ JSON.stringify(results.tokenExpiration, null, 2) }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel v-if="apiTestResult">
            <v-expansion-panel-title>
              🌐 API Test Result
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre>{{ JSON.stringify(apiTestResult, null, 2) }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref } from 'vue'
import { getDashboardSettings } from '@/services/api'
import authDebug from '@/utils/authDebug'

export default {
  name: 'AuthDebugPanel',
  setup() {
    const isLoading = ref(false)
    const isRunningDiagnostic = ref(false)
    const results = ref(null)
    const diagnosticResults = ref(null)
    const apiTestResult = ref(null)

    const runDiagnostic = async () => {
      isRunningDiagnostic.value = true
      try {
        diagnosticResults.value = authDebug.runFullDiagnostic()
        results.value = diagnosticResults.value
      } catch (error) {
        console.error('Diagnostic error:', error)
      } finally {
        isRunningDiagnostic.value = false
      }
    }

    const checkTokenStorage = async () => {
      isLoading.value = true
      try {
        results.value = {
          ...results.value,
          tokenStorage: authDebug.checkTokenStorage(),
        }
      } catch (error) {
        console.error('Token storage check error:', error)
      } finally {
        isLoading.value = false
      }
    }

    const checkStoreAuth = async () => {
      isLoading.value = true
      try {
        results.value = {
          ...results.value,
          storeAuth: authDebug.checkStoreAuthentication(),
        }
      } catch (error) {
        console.error('Store auth check error:', error)
      } finally {
        isLoading.value = false
      }
    }

    const checkTokenExpiration = async () => {
      isLoading.value = true
      try {
        results.value = {
          ...results.value,
          tokenExpiration: authDebug.checkTokenExpiration(),
        }
      } catch (error) {
        console.error('Token expiration check error:', error)
      } finally {
        isLoading.value = false
      }
    }

    const testApiCall = async () => {
      isLoading.value = true
      try {
        console.log(
          '[AuthDebugPanel] 🧪 Testing API call to dashboard settings...'
        )
        const response = await getDashboardSettings()
        apiTestResult.value = {
          success: true,
          status: 'success',
          data: response,
        }
        console.log('[AuthDebugPanel] ✅ API call successful:', response)
      } catch (error) {
        apiTestResult.value = {
          success: false,
          status: 'error',
          error: error.message,
          response: error.response?.data,
        }
        console.error('[AuthDebugPanel] ❌ API call failed:', error)
      } finally {
        isLoading.value = false
      }
    }

    const fixCorruptedTokens = async () => {
      isLoading.value = true
      try {
        console.log('[AuthDebugPanel] 🛠️ Attempting to fix corrupted tokens...')
        const result = authDebug.fixCorruptedTokens()

        if (result.fixed) {
          console.log(
            '[AuthDebugPanel] ✅ Fixed corrupted tokens:',
            result.issues
          )
          // Re-run diagnostic after fixing
          setTimeout(() => {
            runDiagnostic()
          }, 1000)
        } else {
          console.log('[AuthDebugPanel] ℹ️ No corrupted tokens found to fix')
        }
      } catch (error) {
        console.error(
          '[AuthDebugPanel] ❌ Error fixing corrupted tokens:',
          error
        )
      } finally {
        isLoading.value = false
      }
    }

    return {
      isLoading,
      isRunningDiagnostic,
      results,
      diagnosticResults,
      apiTestResult,
      runDiagnostic,
      checkTokenStorage,
      checkStoreAuth,
      checkTokenExpiration,
      testApiCall,
      fixCorruptedTokens,
    }
  },
}
</script>

<style scoped>
.auth-debug-panel {
  margin: 20px;
}

pre {
  font-size: 12px;
  max-height: 400px;
  overflow-y: auto;
}
</style>
