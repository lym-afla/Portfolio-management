<template>
  <router-link
    v-if="id && name"
    :to="{ name: 'SecurityDetail', params: { id } }"
    class="text-primary text-decoration-none font-weight-medium"
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
