<template>
  <v-app>
    <Navigation v-if="isAuthenticated" @logout="handleLogout" />
    <v-main>
      <router-view></router-view>
    </v-main>
  </v-app>
</template>

<script>
import { inject } from 'vue'
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
  setup() {
    const router = useRouter();
    const setUser = inject('setUser');

    const handleLogout = () => {
      setUser(null);
      router.push('/login');
    };

    return { handleLogout };
  }
}
</script>