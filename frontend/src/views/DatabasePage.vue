<template>
  <WorkspacePage
    title="Data"
    description="Inventories that feed the portfolio: brokers, accounts, securities, prices and FX rates."
  >
    <nav aria-label="Data sections" class="database-nav">
      <v-tabs v-model="activeTab" color="primary" density="comfortable" data-testid="database-nav">
        <v-tab to="/database/brokers" value="brokers">Brokers</v-tab>
        <v-tab to="/database/accounts" value="accounts">Accounts</v-tab>
        <v-tab to="/database/securities" value="securities">Securities</v-tab>
        <v-tab to="/database/prices" value="prices">Prices</v-tab>
        <v-tab to="/database/fx" value="fx">FX</v-tab>
      </v-tabs>
    </nav>
    <router-view />
    <WorkspaceSection
      v-if="!activeTab"
      heading-id="database-landing"
      title="Choose an inventory"
      description="Every section keeps its own search, filters and create actions."
      class="database-landing"
    >
      <v-list density="compact" lines="two" class="database-landing__list">
        <v-list-item
          v-for="item in landingItems"
          :key="item.to"
          :to="item.to"
          :title="item.title"
          :prepend-icon="item.icon"
          :subtitle="item.subtitle"
        />
      </v-list>
    </WorkspaceSection>
  </WorkspacePage>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'

const emit = defineEmits(['update-page-title'])
const route = useRoute()
const activeTab = ref(null)

const updateActiveTab = () => {
  const path = route.path
  if (path.includes('/accounts')) {
    activeTab.value = 'accounts'
  } else if (path.includes('/brokers')) {
    activeTab.value = 'brokers'
  } else if (path.includes('/securities')) {
    activeTab.value = 'securities'
  } else if (path.includes('/prices')) {
    activeTab.value = 'prices'
  } else if (path.includes('/fx')) {
    activeTab.value = 'fx'
  }
}

const landingItems = [
  { to: '/database/brokers', title: 'Brokers', icon: 'mdi-bank', subtitle: 'Brokers you invest through, with portfolio totals per broker.' },
  { to: '/database/accounts', title: 'Accounts', icon: 'mdi-wallet-outline', subtitle: 'Investment accounts per broker with cash balances by currency.' },
  { to: '/database/securities', title: 'Securities', icon: 'mdi-file-tree-outline', subtitle: 'The security catalog: identifiers, types, values and detail pages.' },
  { to: '/database/prices', title: 'Prices', icon: 'mdi-chart-line', subtitle: 'Price history per security and date, with imports.' },
  { to: '/database/fx', title: 'FX', icon: 'mdi-currency-exchange', subtitle: 'Exchange-rate grid by date and currency pair.' },
]

const pageTitle = computed(() => {
  switch (activeTab.value) {
    case 'accounts':
      return 'Database – Accounts'
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
</script>

<style scoped>
.database-nav {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.database-landing__list {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
}
</style>
