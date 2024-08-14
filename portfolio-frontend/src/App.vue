<template>
  <v-app>
    <v-overlay :model-value="layoutLoading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <template v-if="!layoutLoading">
      <template v-if="isAuthenticated">
        <Navigation @logout="handleLogout" />
        <v-main>
          <v-container fluid>
            <v-row v-if="pageTitle">
              <v-col>
                <h2 class="text-h4 mb-4">{{ pageTitle }}</h2>
                <v-divider class="mb-4"></v-divider>
              </v-col>
            </v-row>
            <v-row>
              <v-col>
                <BrokerSelection v-if="!isProfilePage" />
              </v-col>
            </v-row>
            <router-view @update-page-title="updatePageTitle"></router-view>
          </v-container>
        </v-main>
      </template>
      <template v-else>
        <v-main>
          <router-view></router-view>
        </v-main>
      </template>
    </template>
  </v-app>
</template>

<script>
import { provide, ref, onMounted, watch, computed } from 'vue'
import Navigation from './components/Navigation.vue'
import BrokerSelection from './components/BrokerSelection.vue'
import { checkAuth } from './utils/auth'
import { useRouter, useRoute } from 'vue-router'

export default {
  name: 'App',
  components: {
    Navigation,
    BrokerSelection,
  },
  setup() {
    const router = useRouter();
    const route = useRoute();
    const user = ref(null);
    const isAuthenticated = ref(false);
    const layoutLoading = ref(true);
    const pageTitle = ref('');

    const isProfilePage = computed(() => {
      return route.path.startsWith('/profile');
    });

    const setUser = (userData) => {
      user.value = userData
    }

    const updateAuthStatus = async () => {
      layoutLoading.value = true;
      isAuthenticated.value = await checkAuth();
      if (!isAuthenticated.value && router.currentRoute.value.meta.requiresAuth) {
        router.push('/login');
      }
      layoutLoading.value = false;
    };

    const handleLogout = () => {
      setUser(null);
      isAuthenticated.value = false;
      router.push('/login');
    };

    const updatePageTitle = (title) => {
      pageTitle.value = title;
    };

    onMounted(async () => {
      await updateAuthStatus();
    });

    watch(() => router.currentRoute.value, async () => {
      layoutLoading.value = true;
      await updateAuthStatus();
    });

    // Reset page title when authentication status changes
    watch(() => isAuthenticated.value, (newValue) => {
      if (!newValue) {
        pageTitle.value = '';
      }
    });

    // Reset page title on route change for non-authenticated routes
    watch(() => router.currentRoute.value.path, () => {
      if (!isAuthenticated.value) {
        pageTitle.value = '';
      }
    });

    provide('user', user)
    provide('setUser', setUser)
    provide('isAuthenticated', isAuthenticated)

    return { 
      user, 
      setUser, 
      router, 
      isAuthenticated, 
      layoutLoading, 
      pageTitle, 
      handleLogout, 
      updatePageTitle,
      isProfilePage,
    };
  },
}
</script>

<style>
html, body {
  overflow-y: auto;
}
</style>