<template>
  <v-container fluid class="mt-4">
    <v-row>
      <v-col cols="12" md="4">
        <!-- Side Navigation -->
        <v-card class="mb-4">
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
        
        <!-- Delete Account Button -->
        <v-card flat class="pa-0">
          <v-btn
            @click="showDeleteConfirmation = true"
            color="error"
            outlined
            block
            class="mt-2"
          >
            <v-icon left>mdi-delete</v-icon>
            Delete Account
          </v-btn>
        </v-card>
      </v-col>
      <v-col cols="12" md="8">
        <!-- Tab Content -->
        <router-view></router-view>
      </v-col>
    </v-row>

    <!-- Delete Account Confirmation Dialog -->
    <v-dialog v-model="showDeleteConfirmation" max-width="400">
      <v-card>
        <v-card-title class="text-h5 error--text">Delete Account</v-card-title>
        <v-card-text>
          <p>
            Are you sure you want to delete your account? This action cannot be
            undone.
          </p>
          <v-text-field
            v-model="confirmationText"
            label="Type 'DELETE' to confirm"
            :rules="[(v) => v === 'DELETE' || 'Please type DELETE to confirm']"
          ></v-text-field>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" text @click="showDeleteConfirmation = false"
            >Cancel</v-btn
          >
          <v-btn
            color="error"
            :disabled="confirmationText !== 'DELETE'"
            @click="deleteAccount"
          >
            Delete Account
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStore } from 'vuex'
import store from '@/store'

export default {
  setup() {
    const router = useRouter()
    const store = useStore()
    const showDeleteConfirmation = ref(false)
    const confirmationText = ref('')

    return { router, store, showDeleteConfirmation, confirmationText }
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
        await store.dispatch('logout')
        // if (response.success) {
        //   this.$emit('update-page-title', '') // Clear the page title
        //   this.router.push('/login')
        // } else {
        //   console.error('Logout failed:', response.error)
        // }
      } catch (error) {
        console.error('Logout error:', error)
      }
    },
    isActive(route) {
      return this.$route.path === route
    },
    async deleteAccount() {
      if (this.confirmationText !== 'DELETE') {
        return
      }
      try {
        const response = await this.store.dispatch('deleteAccount')
        if (response.success) {
          this.router.push('/register')
        } else {
          // Handle error (e.g., show error message to user)
          console.error('Account deletion failed:', response.error)
        }
      } finally {
        this.showDeleteConfirmation = false
        this.confirmationText = ''
      }
    },
  },
  mounted() {
    this.$emit('update-page-title', 'User Profile')
  },
  beforeUnmount() {
    this.$emit('update-page-title', '') // Clear the page title when component is unmounted
  },
}
</script>

<style scoped>
.v-btn.error--text {
  border-color: currentColor;
}
</style>