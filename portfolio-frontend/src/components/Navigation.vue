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
        @click="goToPage('/summary')"
      ></v-list-item>
    </v-list>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-item
        prepend-icon="mdi-monitor-dashboard"
        title="Dashboard"
        value="dashboard"
        to="/dashboard"
        @click="goToPage('/dashboard')"
      ></v-list-item>
      <v-list-item
        prepend-icon="mdi-clipboard-check"
        title="Open Positions"
        value="open"
        to="/open-positions"
        @click="goToPage('/open-positions')"
      ></v-list-item>
      <v-list-item
        prepend-icon="mdi-clipboard-remove"
        title="Closed Positions"
        value="closed"
        to="/closed-positions"
        @click="goToPage('/closed-positions')"
      ></v-list-item>
      <v-list-item
        prepend-icon="mdi-swap-horizontal"
        title="Transactions"
        value="transactions"
        to="/transactions"
        @click="goToPage('/transactions')"
      ></v-list-item>
    </v-list>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-group value="database">
        <template v-slot:activator="{ props }">
          <v-list-item
            v-bind="props"
            prepend-icon="mdi-database"
            title="Database"
            @click="toggleDatabase"
          ></v-list-item>
        </template>

        <v-list-item
          prepend-icon="mdi-bank"
          title="Brokers"
          value="brokers"
          to="/database/brokers"
          @click="goToPage('/database/brokers')"
        ></v-list-item>
        <v-list-item
          prepend-icon="mdi-file-document-outline"
          title="Securities"
          value="securities"
          to="/database/securities"
          @click="goToPage('/database/securities')"
        ></v-list-item>
        <v-list-item
          prepend-icon="mdi-chart-line"
          title="Prices"
          value="prices"
          to="/database/prices"
          @click="goToPage('/database/prices')"
        ></v-list-item>
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
          <template v-slot:append>
            <v-avatar size="36">
              <v-img
                src="https://randomuser.me/api/portraits/men/85.jpg"
                alt="User"
              ></v-img>
            </v-avatar>
          </template>
        </v-list-item>
      </v-list>
    </template>
  </v-navigation-drawer>
</template>

<script>
import { mapState, mapActions } from 'vuex'

export default {
  data: () => ({
    drawer: true,
    extended: false,
    databaseExpanded: false,
  }),
  computed: {
    ...mapState(['effectiveCurrentDate']),
  },
  methods: {
    ...mapActions(['fetchEffectiveCurrentDate']),
    toggleExtended() {
      this.extended = !this.extended
    },
    toggleDatabase() {
      this.databaseExpanded = !this.databaseExpanded
      if (this.databaseExpanded) {
        this.extended = true
      }
    },
    goToPage(route) {
      this.$router.push(route)
      if (!this.databaseExpanded && route !== '/profile') {
        this.extended = false
      }
    },
  },
  mounted() {
    this.fetchEffectiveCurrentDate()
  }
}
</script>