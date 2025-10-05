<template>
  <span class="text-caption text-grey"> || Fee: {{ commission }} </span>
</template>

<script>
export default {
  name: 'CommissionDisplay',
  props: {
    commission: {
      type: String,
      required: true,
    },
  },
}
</script>
