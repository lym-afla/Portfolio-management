<template>
  <v-container fluid class="mt-4">
    <v-row>
      <v-col cols="12" md="4">
        <!-- Side Navigation -->
        <v-card>
          <v-list>
            <v-list-item
              v-for="(item, i) in menuItems"
              :key="i"
              :to="item.to"
              :active="isActive(item.to)"
              active-class="primary white--text"
            >
              <v-list-item-title>{{ item.title }}</v-list-item-title>
            </v-list-item>
          </v-list>
          <v-divider></v-divider>
          <v-list-item @click="logout">
            <v-list-item-title>Logout</v-list-item-title>
          </v-list-item>
        </v-card>
      </v-col>
      <v-col cols="12" md="8">
        <!-- Tab Content -->
        <router-view></router-view>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { useRouter } from 'vue-router';
import axios from 'axios';

export default {
  setup() {
    const router = useRouter();
    return { router };
  },
  data() {
    return {
      menuItems: [
        { title: 'User details', to: '/profile' },
        { title: 'Settings', to: '/profile/settings' },
      ],
    }
  },
  methods: {
    async logout() {
      try {
        // Call the logout API endpoint
        await axios.post('/users/api/logout/');
        
        // Clear the authentication token from local storage
        localStorage.removeItem('token');
        
        // Redirect to login page
        this.router.push('/login');
      } catch (error) {
        console.error('Logout failed:', error);
        // Even if the API call fails, clear the token and redirect
        localStorage.removeItem('token');
        this.router.push('/login');
      }
    },
    isActive(route) {
      return this.$route.path === route;
    },
  },
}
</script>