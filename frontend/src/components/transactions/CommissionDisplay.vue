<template>
  <span class="text-caption text-grey"> || Fee: {{ commission }} </span>
</template>

<script setup>
defineProps({
  commission: {
    type: String,
    required: true,
  },
})
</script>
