<template>
  <div class="broker-selection">
    <v-card flat>
      <v-card-text class="pa-0">
        <div class="d-flex align-center">
          <v-btn
            @click="switchBroker(-1)"
            :disabled="!canSwitchLeft"
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-left</v-icon>
          </v-btn>
          <v-select
            v-model="selectedBroker"
            :items="brokerOptions"
            item-title="title"
            item-value="value"
            label="Select Broker"
            density="comfortable"
            hide-details
            @update:model-value="handleBrokerChange"
            class="broker-select mx-2"
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
            @click="switchBroker(1)"
            :disabled="!canSwitchRight"
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-right</v-icon>
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
    <v-divider class="mt-2"></v-divider>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useStore } from 'vuex'
import { getBrokerChoices, updateUserBroker } from '@/services/api'
import { formatBrokerChoices } from '@/utils/brokerUtils'

export default {
  name: 'BrokerSelection',
  setup() {
    const store = useStore()
    const brokerOptions = ref([])
    const selectedBroker = ref(null)

    const currentIndex = computed(() => {
      return brokerOptions.value.findIndex(option => option.value === selectedBroker.value)
    })

    const canSwitchLeft = computed(() => {
      return brokerOptions.value.slice(0, currentIndex.value).some(option => option.type === 'option')
    })

    const canSwitchRight = computed(() => {
      return brokerOptions.value.slice(currentIndex.value + 1).some(option => option.type === 'option')
    })

    const fetchBrokers = async () => {
      try {
        const data = await getBrokerChoices()
        brokerOptions.value = formatBrokerChoices(data.options)
        selectedBroker.value = data.custom_brokers
      } catch (error) {
        console.error('Error fetching brokers:', error)
      }
    }

    const handleBrokerChange = async (newValue) => {
      console.log('handleBrokerChange called with:', newValue)
      if (typeof newValue === 'object' && newValue !== null) {
        selectedBroker.value = newValue.value
        await updateDataForBroker(newValue.value)
        store.dispatch('updateSelectedBroker', newValue)
      } else {
        selectedBroker.value = newValue
        await updateDataForBroker(newValue)
        store.dispatch('updateSelectedBroker', newValue)
      }
    }

    const updateDataForBroker = async (brokerValue) => {
      try {
        console.log('updateDataForBroker called with:', brokerValue)
        const response = await updateUserBroker(brokerValue)
        console.log('updateUserBroker response:', response)
        store.dispatch('setCustomBrokers', brokerValue)
        store.dispatch('triggerDataRefresh')
      } catch (error) {
        console.error('Error updating broker:', error)
      }
    }

    const switchBroker = (direction) => {
      console.log('switchBroker called with direction:', direction)
      let newIndex = currentIndex.value + direction

      // Skip dividers and headers
      while (newIndex >= 0 && newIndex < brokerOptions.value.length) {
        const currentOption = brokerOptions.value[newIndex]
        if (currentOption.type === 'option') {
          break
        }
        newIndex += direction
      }

      // Check if the new index is valid
      if (newIndex >= 0 && newIndex < brokerOptions.value.length) {
        const newBroker = brokerOptions.value[newIndex]
        console.log('Switching to broker:', newBroker)
        handleBrokerChange(newBroker)
      }
    }

    onMounted(() => {
      console.log('BrokerSelection component mounted')
      fetchBrokers()
    })

    return {
      brokerOptions,
      selectedBroker,
      currentIndex,
      handleBrokerChange,
      switchBroker,
      canSwitchLeft,
      canSwitchRight
    }
  }
}
</script>

<style scoped>
.broker-selection {
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

.broker-select {
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