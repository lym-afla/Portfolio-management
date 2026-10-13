<template>
  <!-- Modernized link styling (presentation only): restrained primary color,
       underline on hover/focus; the shared focus outline and router-link
       semantics stay. -->
  <router-link
    v-if="id && name"
    :to="{ name: 'SecurityDetail', params: { id } }"
    class="security-link"
  >
    {{ name }}
  </router-link>
  <span v-else>–</span>
</template>

<script setup>
defineProps({
  id: {
    type: [Number, String],
    default: null,
  },
  name: {
    type: String,
    default: null,
  },
})
</script>
