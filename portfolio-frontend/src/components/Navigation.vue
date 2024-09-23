<template>
  <v-navigation-drawer v-model="drawer" :rail="!extended" permanent>
    <v-list-item
      @click="toggleExtended"
      prepend-icon="mdi-menu"
      title="Menu"
    ></v-list-item>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-item
        prepend-icon="mdi-apps"
        title="Summary"
        value="summary"
        to="/summary"
        :active="isActive('/summary')"
        @click="goToPage('/summary')"
      ></v-list-item>
    </v-list>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-item
        v-for="item in menuItems"
        :key="item.title"
        :prepend-icon="item.icon"
        :title="item.title"
        :value="item.value"
        :to="item.to"
        :active="isActive(item.to)"
        @click="goToPage(item.to)"
      ></v-list-item>
    </v-list>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-group value="database" :mandatory="false">
        <template v-slot:activator="{ props }">
          <v-list-item
            v-bind="props"
            prepend-icon="mdi-database"
            title="Database"
            :active="isActive('/database')"
            @click="handleDatabaseClick"
          ></v-list-item>
        </template>

        <template v-if="extended">
          <v-list-item
            v-for="subItem in databaseSubItems"
            :key="subItem.title"
            :prepend-icon="subItem.icon"
            :title="subItem.title"
            :to="subItem.to"
            :active="isActive(subItem.to)"
            @click="goToPage(subItem.to)"
          ></v-list-item>
        </template>
      </v-list-group>
    </v-list>

    <template v-slot:append>
      <v-divider></v-divider>
      <v-list density="compact" nav>
        <v-list-item
          prepend-icon="mdi-calendar"
          :title="effectiveCurrentDate || 'No date set'"
          value="effective-date"
        ></v-list-item>
        <v-list-item
          prepend-icon="mdi-account-circle"
          title="Profile"
          value="profile"
          to="/profile"
        >
          <!-- <template v-slot:append>
            <v-avatar size="36">
              <v-img
                src="https://randomuser.me/api/portraits/men/85.jpg"
                alt="User"
              ></v-img>
            </v-avatar>
          </template> -->
        </v-list-item>
      </v-list>
    </template>
  </v-navigation-drawer>
</template>

<script>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStore } from 'vuex'

export default {
  name: 'Navigation',
  setup() {
    const drawer = ref(true)
    const extended = ref(true)
    const route = useRoute()
    const router = useRouter()
    const store = useStore()
    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const menuItems = [
      { title: 'Dashboard', icon: 'mdi-monitor-dashboard', value: 'dashboard', to: '/dashboard' },
      { title: 'Open Positions', icon: 'mdi-clipboard-check', value: 'open', to: '/open-positions' },
      { title: 'Closed Positions', icon: 'mdi-clipboard-remove', value: 'closed', to: '/closed-positions' },
      { title: 'Transactions', icon: 'mdi-swap-horizontal', value: 'transactions', to: '/transactions' },
    ]

    const databaseSubItems = [
      { title: 'Brokers', icon: 'mdi-bank', to: '/database/brokers' },
      { title: 'Prices', icon: 'mdi-file-document-outline', to: '/database/prices' },
      { title: 'Securities', icon: 'mdi-chart-line', to: '/database/securities' },
      { title: 'FX', icon: 'mdi-currency-usd', to: '/database/fx' },
    ]

    const toggleExtended = () => {
      extended.value = !extended.value
    }

    const isActive = (path) => {
      if (path === '/database') {
        // Check if current route is database or any of its children
        return route.path.startsWith('/database')
      }
      return route.path === path
    }

    const goToPage = (path) => {
      router.push(path)
    }

    const handleDatabaseClick = () => {
      if (!extended.value) {
        extended.value = true
      // } else {
      //   // If already extended, navigate to a default database page or toggle the group
      //   router.push('/database') // or any default database route
      }
    }

    return {
      drawer,
      extended,
      menuItems,
      databaseSubItems,
      toggleExtended,
      isActive,
      goToPage,
      effectiveCurrentDate,
      handleDatabaseClick,
    }
  }
}
</script>