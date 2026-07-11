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

<script>
export default {
  name: 'SecurityLink',
  props: {
    id: {
      type: [Number, String],
      default: null,
    },
    name: {
      type: String,
      default: null,
    },
  },
}
</script>
