<template>
  <span class="text-caption text-grey"> || ACI: {{ aci }} </span>
</template>

<script>
export default {
  name: 'AciDisplay',
  props: {
    aci: {
      type: String,
      required: true,
    },
  },
}
</script>
