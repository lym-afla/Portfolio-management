<template>
  <v-container fluid class="database-page pa-0">
    <v-row>
      <v-col cols="12">
        <v-tabs
          v-model="activeTab"
          color="primary"
          align-tabs="center"
        >
          <v-tab to="/database/brokers" value="brokers">Brokers</v-tab>
          <v-tab to="/database/securities" value="securities">Securities</v-tab>
          <v-tab to="/database/prices" value="prices">Prices</v-tab>
          <v-tab to="/database/fx" value="fx">FX</v-tab>
        </v-tabs>
      </v-col>
    </v-row>
    <v-row>
      <v-col cols="12">
        <router-view></router-view>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'

export default {
  name: 'DatabasePage',
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const route = useRoute()
    const activeTab = ref(null)

    const updateActiveTab = () => {
      const path = route.path
      if (path.includes('/brokers')) {
        activeTab.value = 'brokers'
      } else if (path.includes('/securities')) {
        activeTab.value = 'securities'
      } else if (path.includes('/prices')) {
        activeTab.value = 'prices'
      } else if (path.includes('/fx')) {
        activeTab.value = 'fx'
      }
    }

    const pageTitle = computed(() => {
      switch (activeTab.value) {
        case 'brokers':
          return 'Database – Brokers'
        case 'securities':
          return 'Database – Securities'
        case 'prices':
          return 'Database – Prices'
        case 'fx':
          return 'Database – FX'
        default:
          return 'Database'
      }
    })

    watch(() => route.path, updateActiveTab)

    onMounted(() => {
      updateActiveTab()
      emit('update-page-title', pageTitle.value)
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    watch(pageTitle, (newTitle) => {
      emit('update-page-title', newTitle)
    })

    return {
      activeTab
    }
  }
}
</script>

<style scoped>
.database-page {
  min-height: 100vh;
}
</style>