<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      Broker API Tokens
      <v-spacer></v-spacer>
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="showAddTokenDialog = true"
      >
        Add Token
      </v-btn>
    </v-card-title>

    <v-card-text>
      <v-checkbox
        v-model="showInactiveTokens"
        label="Show inactive tokens"
        hide-details
        class="mb-4"
      ></v-checkbox>

      <v-progress-linear
        v-if="loading"
        indeterminate
        color="primary"
      ></v-progress-linear>

      <v-expansion-panels v-else>
        <!-- Tinkoff Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bank</v-icon>
            Tinkoff tokens ({{ filteredTinkoffTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredTinkoffTokens.length">
              <v-list-item
                v-for="token in filteredTinkoffTokens"
                :key="token.id"
              >
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="token.is_active ? 'mdi-check-circle' : 'mdi-close-circle'"
                        class="mr-2"
                      ></v-icon>
                    </template>
                    {{ token.is_active ? 'Valid token' : 'Invalid token' }}
                  </v-tooltip>
                </template>
                
                <v-list-item-title>
                  {{ token.token_type === 'read_only' ? 'Read Only Token' : 'Full Access Token' }}
                </v-list-item-title>
                
                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>
                
                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-refresh"
                        variant="text"
                        color="primary"
                        @click="testConnection('tinkoff', token.id)"
                        :loading="isTestingConnection[`tinkoff-${token.id}`]"
                      ></v-btn>
                    </template>
                    Check token validity
                  </v-tooltip>

                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="revokeToken('tinkoff', token.id)"
                      ></v-btn>
                    </template>
                    Revoke token
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert
              v-else
              type="info"
              variant="tonal"
              class="mt-2"
            >
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Interactive Brokers Tokens -->
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start>mdi-bank</v-icon>
            Interactive Brokers tokens ({{ filteredIBTokens.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-list v-if="filteredIBTokens.length">
              <v-list-item
                v-for="token in filteredIBTokens"
                :key="token.id"
              >
                <template v-slot:prepend>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        v-bind="props"
                        :color="token.is_active ? 'success' : 'error'"
                        :icon="token.is_active ? 'mdi-check-circle' : 'mdi-close-circle'"
                        class="mr-2"
                      ></v-icon>
                    </template>
                    {{ token.is_active ? 'Valid token' : 'Invalid token' }}
                  </v-tooltip>
                </template>
                
                <v-list-item-title>
                  Account: {{ token.account_id }}
                </v-list-item-title>
                
                <v-list-item-subtitle>
                  Created on {{ formatDate(token.created_at) }}
                  <v-chip
                    v-if="token.paper_trading"
                    color="warning"
                    size="small"
                    class="ml-2"
                  >
                    Paper Trading
                  </v-chip>
                  <v-chip
                    v-if="!token.is_active"
                    color="error"
                    size="small"
                    class="ml-2"
                  >
                    Inactive
                  </v-chip>
                </v-list-item-subtitle>
                
                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-refresh"
                        variant="text"
                        color="primary"
                        @click="testConnection('ib', token.id)"
                        :loading="isTestingConnection[`ib-${token.id}`]"
                      ></v-btn>
                    </template>
                    Check token validity
                  </v-tooltip>

                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="revokeToken('ib', token.id)"
                      ></v-btn>
                    </template>
                    Revoke token
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
            <v-alert
              v-else
              type="info"
              variant="tonal"
              class="mt-2"
            >
              No tokens found
            </v-alert>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>

    <!-- Add Token Dialog -->
    <v-dialog v-model="showAddTokenDialog" max-width="500px">
      <v-card>
        <v-card-title>Add New Token</v-card-title>
        <v-card-text>
          <v-form ref="form" v-model="isFormValid">
            <v-select
              v-model="newToken.broker"
              :items="brokerOptions"
              label="Broker"
              required
            ></v-select>

            <v-text-field
              v-model="newToken.token"
              label="API Token"
              type="password"
              required
              :rules="[v => !!v || 'Token is required']"
            ></v-text-field>

            <template v-if="newToken.broker === 'ib'">
              <v-text-field
                v-model="newToken.account_id"
                label="Account ID"
                required
                :rules="[v => !!v || 'Account ID is required']"
              ></v-text-field>
              <v-switch
                v-model="newToken.paper_trading"
                label="Paper Trading"
                color="primary"
                :true-value="true"
                :false-value="false"
                :true-icon="'mdi-check'"
                :false-icon="'mdi-close'"
                hide-details
              ></v-switch>
            </template>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            @click="saveToken"
            :loading="isSaving"
            :disabled="!isFormValid"
          >
            Save
          </v-btn>
          <v-btn
            color="error"
            @click="showAddTokenDialog = false"
          >
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import { getBrokerTokens, saveTinkoffToken, saveIBToken, testTinkoffConnection, testIBConnection, revokeToken } from '@/services/api'

export default {
  name: 'BrokerTokenManager',
  
  emits: ['error', 'success'],
  
  data() {
    return {
      loading: true,
      form: null,
      isFormValid: false,
      showAddTokenDialog: false,
      isSaving: false,
      isTestingConnection: {},
      tinkoffTokens: [],
      ibTokens: [],
      newToken: {
        broker: '',
        token: '',
        account_id: '',
        paper_trading: false
      },
      brokerOptions: [
        { title: 'Tinkoff', value: 'tinkoff' },
        { title: 'Interactive Brokers', value: 'ib' }
      ],
      showInactiveTokens: false
    }
  },

  computed: {
    filteredTinkoffTokens() {
      return this.tinkoffTokens.filter(token => 
        this.showInactiveTokens ? true : token.is_active
      )
    },

    filteredIBTokens() {
      return this.ibTokens.filter(token => 
        this.showInactiveTokens ? true : token.is_active
      )
    }
  },

  methods: {
    handleError(error) {
      let errorMessage = 'An unexpected error occurred.'
      
      if (error.response?.data?.error) {
        errorMessage = error.response.data.error
      } else if (error.response?.status === 403) {
        errorMessage = 'You do not have permission to access this resource.'
      } else if (error.request) {
        errorMessage = 'The server did not respond. Please check your internet connection.'
      } else if (error.message) {
        errorMessage = error.message
      }

      this.$emit('error', errorMessage)
    },

    async fetchTokens() {
      console.log('Attempting to fetch tokens...')
      this.loading = true
      try {
        console.log('Making API call to getBrokerTokens...')
        const response = await getBrokerTokens()
        console.log('API response:', response)
        if (response) {
          this.tinkoffTokens = response.tinkoff_tokens || []
          this.ibTokens = response.ib_tokens || []
        }
      } catch (error) {
        console.error('Error in fetchTokens:', error)
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },

    async saveToken() {
      this.isSaving = true
      try {
        if (this.newToken.broker === 'tinkoff') {
          await saveTinkoffToken({
            token: this.newToken.token
          })
        } else if (this.newToken.broker === 'ib') {
          await saveIBToken({
            token: this.newToken.token,
            account_id: this.newToken.account_id,
            paper_trading: this.newToken.paper_trading
          })
        }
        await this.fetchTokens()
        this.showAddTokenDialog = false
        this.$refs.form?.reset()
        this.$emit('success', 'Token saved successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isSaving = false
      }
    },

    async testConnection(broker, tokenId) {
      const key = `${broker}-${tokenId}`
      this.isTestingConnection[key] = true
      try {
        if (broker === 'tinkoff') {
          await testTinkoffConnection(tokenId)
          this.$emit('success', 'Connection test successful')
        } else if (broker === 'ib') {
          await testIBConnection(tokenId)
          this.$emit('success', 'Connection test successful')
        }
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isTestingConnection[key] = false
      }
    },

    async revokeToken(broker, tokenId) {
      try {
        await revokeToken(broker, tokenId)
        await this.fetchTokens()
        this.$emit('success', 'Token revoked successfully')
      } catch (error) {
        this.handleError(error)
      }
    },

    formatDate(dateString) {
      const date = new Date(dateString)
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      }).replace(/ /g, '-')
    }
  },

  created() {
    console.log('BrokerTokenManager component created')
  },

  async mounted() {
    console.log('BrokerTokenManager component mounted')
    await this.fetchTokens()
  }
}
</script> 