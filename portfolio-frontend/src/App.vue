<template>
  <AppLayout :is-authenticated="isAuthenticated" />
</template>

<script>
import { provide, ref, onMounted, watch } from 'vue'
import AppLayout from './components/AppLayout.vue'
import { checkAuth } from './utils/auth'
import { useRouter } from 'vue-router'

export default {
  name: 'App',
  components: {
    AppLayout,
  },
  setup() {
    const router = useRouter();
    const user = ref(null);
    const isAuthenticated = ref(false);

    const setUser = (userData) => {
      user.value = userData
    }

    const updateAuthStatus = async () => {
      isAuthenticated.value = await checkAuth();
      if (!isAuthenticated.value && router.currentRoute.value.meta.requiresAuth) {
        router.push('/login');
      }
    };

    onMounted(updateAuthStatus);
    watch(() => router.currentRoute.value, updateAuthStatus);

    provide('user', user)
    provide('setUser', setUser)
    provide('isAuthenticated', isAuthenticated)

    return { user, setUser, router, isAuthenticated };
  },
}
</script>