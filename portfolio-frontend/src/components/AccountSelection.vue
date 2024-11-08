<template>
  <div class="account-selection">
    <v-card flat>
      <v-card-text class="pa-0">
        <div class="d-flex align-center">
          <v-btn
            @click="switchAccount(-1)"
            :disabled="!canSwitchLeft"
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-left</v-icon>
          </v-btn>
          <v-select
            v-model="selectedAccount"
            :items="accountOptions"
            item-title="title"
            item-value="value"
            label="Account or Account group"
            density="comfortable"
            hide-details
            @update:model-value="handleAccountChange"
            class="account-select mx-2"
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-if="item.raw.type === 'option'" v-bind="props" :title="null">
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
              <v-list-subheader v-else-if="item.raw.type === 'header'" class="custom-subheader">
                {{ item.raw.title }}
              </v-list-subheader>
            </template>
          </v-select>
          <v-btn
            @click="switchAccount(1)"
            :disabled="!canSwitchRight"
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-right</v-icon>
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useStore } from 'vuex'
import { getAccountChoices, updateForNewAccount } from '@/services/api'
import { formatAccountChoices } from '@/utils/accountUtils'

export default {
  name: 'AccountSelection',
  setup() {
    const store = useStore()
    const accountOptions = ref([])
    const selectedAccount = ref(null)

    const currentIndex = computed(() => {
      return accountOptions.value.findIndex(option => option.value === selectedAccount.value)
    })

    const canSwitchLeft = computed(() => {
      return accountOptions.value.slice(0, currentIndex.value).some(option => option.type === 'option')
    })

    const canSwitchRight = computed(() => {
      return accountOptions.value.slice(currentIndex.value + 1).some(option => option.type === 'option')
    })

    const fetchAccounts = async () => {
      try {
        const data = await getAccountChoices()
        accountOptions.value = formatAccountChoices(data.options)
        selectedAccount.value = data.custom_broker_accounts
      } catch (error) {
        console.error('Error fetching broker accounts:', error)
      }
    }

    const handleAccountChange = async (newValue) => {
      console.log('handleBrokerAccountChange called with:', newValue)
      if (typeof newValue === 'object' && newValue !== null) {
        selectedAccount.value = newValue.value
        await updateDataForBrokerAccount(newValue.value)
      } else {
        selectedAccount.value = newValue
        await updateDataForBrokerAccount(newValue)
      }
    }

    const updateDataForBrokerAccount = async (brokerAccountValue) => {
      try {
        console.log('updateDataForBrokerAccount called with:', brokerAccountValue)
        const response = await updateForNewAccount(brokerAccountValue)
        console.log('updateUserBrokerAccount response:', response)
        store.dispatch('triggerDataRefresh')
      } catch (error) {
        console.error('Error updating broker account:', error)
      }
    }

    const switchAccount = (direction) => {
      console.log('switchAccount called with direction:', direction)
      let newIndex = currentIndex.value + direction

      // Skip dividers and headers
      while (newIndex >= 0 && newIndex < accountOptions.value.length) {
        const currentOption = accountOptions.value[newIndex]
        if (currentOption.type === 'option') {
          break
        }
        newIndex += direction
      }

      // Check if the new index is valid
      if (newIndex >= 0 && newIndex < accountOptions.value.length) {
        const newBrokerAccount = accountOptions.value[newIndex]
        console.log('Switching to broker account:', newBrokerAccount)
        handleAccountChange(newBrokerAccount)
      }
    }

    onMounted(() => {
      console.log('AccountSelection component mounted')
      fetchAccounts()
    })

    return {
      accountOptions,
      selectedAccount,
      currentIndex,
      handleAccountChange,
      switchAccount,
      canSwitchLeft,
      canSwitchRight
    }
  }
}
</script>

<style scoped>
.account-selection {
  --select-height: 56px;
}

.custom-subheader {
  font-weight: bold;
  font-size: 1.1em;
  color: #000000;
  padding-top: 12px;
  padding-bottom: 12px;
  background-color: #F5F5F5;
}

.arrow-btn {
  width: var(--select-height);
  height: var(--select-height);
  min-width: 0 !important;
  padding: 0 !important;
}

.account-select {
  flex-grow: 1;
}

.v-card-text {
  padding: 8px 0;
}

:deep(.v-field__input) {
  min-height: var(--select-height) !important;
}

:deep(.v-field__outline) {
  --v-field-border-width: 1px !important;
}
</style>