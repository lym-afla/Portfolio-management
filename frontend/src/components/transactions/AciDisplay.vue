<template>
  <span class="text-caption text-grey"> || ACI: {{ aci }} </span>
</template>

<script setup>
defineProps({
  aci: {
    type: String,
    required: true,
  },
})
</script>
