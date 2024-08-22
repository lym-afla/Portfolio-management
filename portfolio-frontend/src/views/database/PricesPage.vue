<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12" sm="6" md="2">
        <v-select
          v-model="selectedAssetTypes"
          :items="assetTypes"
          label="Asset Types"
          multiple
          chips
        ></v-select>
      </v-col>
      <v-col cols="12" sm="6" md="2">
        <v-select
          v-model="selectedBroker"
          :items="brokers"
          label="Brokers"
          item-title="name"
          item-value="id"
        ></v-select>
      </v-col>
      <v-col cols="12" sm="6" md="2">
        <v-select
          v-model="selectedSecurities"
          :items="securities"
          label="Securities"
          multiple
          chips
          item-title="name"
          item-value="id"
        ></v-select>
      </v-col>
      <v-col cols="12" sm="6" md="2">
        <v-text-field
          v-model="startDate"
          label="Start Date"
          type="date"
        ></v-text-field>
      </v-col>
      <v-col cols="12" sm="6" md="2">
        <v-text-field
          v-model="endDate"
          label="End Date"
          type="date"
        ></v-text-field>
      </v-col>
    </v-row>
    <v-row>
      <v-col>
        <v-btn color="primary" @click="applyFilters">Apply Filters</v-btn>
        <v-btn color="success" class="ml-2" @click="showImportModal">Import Prices</v-btn>
      </v-col>
    </v-row>
    <!-- Price data table will be added here -->
  </v-container>
</template>

<script>
import { ref, onMounted } from 'vue';
import { getAssetTypes, getBrokers, getSecurities } from '@/services/api';

export default {
  name: 'PricesPage',
  setup() {
    const assetTypes = ref([]);
    const brokers = ref([]);
    const securities = ref([]);
    const selectedAssetTypes = ref([]);
    const selectedBroker = ref(null);
    const selectedSecurities = ref([]);
    const startDate = ref('');
    const endDate = ref('');

    onMounted(async () => {
      try {
        assetTypes.value = await getAssetTypes();
        brokers.value = await getBrokers();
        securities.value = await getSecurities();
      } catch (error) {
        console.error('Error fetching initial data:', error);
      }
    });

    const applyFilters = () => {
      // TODO: Implement filter application logic
      console.log('Applying filters');
    };

    const showImportModal = () => {
      // TODO: Implement import modal logic
      console.log('Showing import modal');
    };

    return {
      assetTypes,
      brokers,
      securities,
      selectedAssetTypes,
      selectedBroker,
      selectedSecurities,
      startDate,
      endDate,
      applyFilters,
      showImportModal,
    };
  },
};
</script>