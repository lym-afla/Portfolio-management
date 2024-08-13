<template>
  <v-app>
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
          <router-view @update-page-title="updatePageTitle"></router-view>
        </v-container>
      </v-main>
    </template>
    <template v-else>
      <v-main>
        <router-view></router-view>
      </v-main>
    </template>
  </v-app>
</template>

<script>
import { ref, inject, watch } from 'vue'
import Navigation from './Navigation.vue'
import { useRouter } from 'vue-router'

export default {
  components: {
    Navigation,
  },
  props: {
    isAuthenticated: {
      type: Boolean,
      required: true
    }
  },
  setup(props) {
    const router = useRouter();
    const setUser = inject('setUser');
    const pageTitle = ref('');

    const handleLogout = () => {
      setUser(null);
      router.push('/login');
    };

    const updatePageTitle = (title) => {
      pageTitle.value = title;
    };

    // Reset page title when authentication status changes
    watch(() => props.isAuthenticated, (newValue) => {
      if (!newValue) {
        pageTitle.value = '';
      }
    });

    // Reset page title on route change for non-authenticated routes
    watch(() => router.currentRoute.value.path, () => {
      if (!props.isAuthenticated) {
        pageTitle.value = '';
      }
    });

    return { handleLogout, pageTitle, updatePageTitle };
  }
}
</script>