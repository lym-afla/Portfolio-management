<template>
  <v-card v-if="showSecurityMapping" class="mt-4">
    <v-card-title class="text-h6 d-flex align-center">
      <v-icon start color="primary" icon="mdi-link-variant" class="mr-2" />
      Map Security
    </v-card-title>
    <v-card-text>
      <v-alert type="warning" variant="tonal" class="mb-4">
        <div class="text-subtitle-1 font-weight-medium">
          Unrecognized security
        </div>
        <div class="text-body-2">{{ security }}</div>
      </v-alert>

      <v-alert v-if="bestMatch" type="info" variant="tonal" class="mb-4">
        <div class="text-subtitle-1 font-weight-medium">Best match found</div>
        <div class="text-body-2">
          {{ bestMatch.match_name }} (Score: {{ bestMatch.match_score }})
        </div>
      </v-alert>

      <v-autocomplete
        v-model="selectedSecurity"
        :items="securityOptions"
        label="Select Security"
        item-title="name"
        item-value="id"
        :loading="loadingSecurities"
        :disabled="loadingSecurities"
        :error-messages="securityError"
        variant="outlined"
        class="mt-2"
      >
        <template v-slot:prepend-inner>
          <v-icon color="primary">mdi-magnify</v-icon>
        </template>
      </v-autocomplete>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, watch, onMounted } from 'vue'
import { getSecurities } from '@/services/api'
import logger from '@/utils/logger'

export default {
  name: 'SecurityMappingDialog',
  props: {
    showSecurityMapping: {
      type: Boolean,
      default: false,
    },
    security: String,
    bestMatch: Object,
  },
  emits: ['security-selected'],
  setup(props, { emit }) {
    logger.log('Unknown', 'SecurityMappingDialog setup called')

    const selectedSecurity = ref(null)
    const securityOptions = ref([])
    const loadingSecurities = ref(false)
    const securityError = ref(null)

    const fetchSecurities = async () => {
      loadingSecurities.value = true
      securityError.value = null
      try {
        const securities = await getSecurities()
        logger.log('Unknown', 'Fetched securities:', securities)
        if (Array.isArray(securities)) {
          securityOptions.value = securities.map((security) => ({
            id: security.id,
            name: security.name,
          }))
          selectedSecurity.value = props.bestMatch.match_id
          console.log(
            'Assigning value to Select',
            props.bestMatch.match_id,
            props.bestMatch.match_name,
            selectedSecurity.value
          )
        } else {
          logger.error('Unknown', 'Fetched securities is not an array:', securities)
          securityError.value = 'Invalid data received from server'
        }
      } catch (error) {
        logger.error('Unknown', 'Error fetching securities:', error)
        securityError.value = 'Failed to fetch securities'
      } finally {
        loadingSecurities.value = false
      }
    }

    // watch(() => props.accountId, (newValue) => {
    //   logger.log('Unknown', 'accountId changed:', newValue)
    //   if (newValue) {
    //     fetchSecurities()
    //   }
    // }, { immediate: true })

    watch(
      () => selectedSecurity.value,
      (newValue) => {
        emit('security-selected', newValue)
      }
    )

    onMounted(fetchSecurities)

    return {
      selectedSecurity,
      securityOptions,
      loadingSecurities,
      securityError,
    }
  },
}
</script>
