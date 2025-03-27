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
              <v-list-item
                v-if="item.raw.type === 'option'"
                v-bind="props"
                :title="null"
              >
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
              <v-list-subheader
                v-else-if="item.raw.type === 'header'"
                class="custom-subheader"
              >
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
import { getAccountChoices } from '@/services/api'
import { formatAccountChoices } from '@/utils/accountUtils'

export default {
  name: 'AccountSelection',
  setup() {
    const store = useStore()
    const accountOptions = ref([])
    const selectedAccount = ref(null)

    const currentIndex = computed(() => {
      if (!selectedAccount.value) return -1
      return accountOptions.value.findIndex(
        (option) =>
          option.type === 'option' &&
          option.value.type === selectedAccount.value.type &&
          option.value.id === selectedAccount.value.id
      )
    })

    const canSwitchLeft = computed(() => {
      return accountOptions.value
        .slice(0, currentIndex.value)
        .some((option) => option.type === 'option')
    })

    const canSwitchRight = computed(() => {
      return accountOptions.value
        .slice(currentIndex.value + 1)
        .some((option) => option.type === 'option')
    })

    const fetchAccounts = async () => {
      try {
        const data = await getAccountChoices()
        accountOptions.value = formatAccountChoices(data.options)
        // Find the option matching the selected type and id
        const selected = data.selected
        const matchingOption = accountOptions.value.find(
          (option) =>
            option.type === 'option' &&
            option.value.type === selected.type &&
            option.value.id === selected.id
        )
        selectedAccount.value = matchingOption?.value || null
        store.dispatch('updateSelectedAccount', selectedAccount.value)
      } catch (error) {
        console.error('Error fetching accounts:', error)
      }
    }

    const handleAccountChange = async (newValue) => {
      console.log('handleAccountChange called with:', newValue)
      selectedAccount.value = newValue

      await store.dispatch('updateAccountSelection', {
        type: newValue.type,
        id: newValue.id,
      })

      // Log the updated store state after the dispatch completes
      console.log(
        '[handleAccountChange] store.state.accountSelection:',
        store.state.accountSelection
      )

      // // Update data for the new account
      // await updateDataForAccount(newValue)
    }

    // const updateDataForAccount = async (selection) => {
    //   try {
    //     console.log('updateDataForAccount called with:', selection)
    //     const response = await updateUserDataForNewAccount({
    //       type: selection.type,
    //       id: selection.id
    //     })
    //     console.log('updateForNewAccount response:', response)
    //     store.dispatch('triggerDataRefresh')
    //   } catch (error) {
    //     console.error('Error updating account selection:', error)
    //   }
    // }

    const switchAccount = (direction) => {
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
        const newAccount = accountOptions.value[newIndex]
        handleAccountChange(newAccount.value)
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
      canSwitchRight,
    }
  },
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
  background-color: #f5f5f5;
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
