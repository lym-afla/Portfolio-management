<template>
  <v-btn-toggle
    :model-value="modelValue"
    mandatory
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-btn value="7d">7d</v-btn>
    <v-btn value="1m">1m</v-btn>
    <v-btn value="3m">3m</v-btn>
    <v-btn value="6m">6m</v-btn>
    <v-btn v-if="showYTD" value="ytd">YTD</v-btn>
    <v-btn value="1Y">1Y</v-btn>
    <v-btn value="3Y">3Y</v-btn>
    <v-btn value="5Y">5Y</v-btn>
    <v-btn value="All">All</v-btn>
  </v-btn-toggle>
</template>

<script>
import { computed } from 'vue'

export default {
  name: 'TimelineSelector',
  props: {
    modelValue: {
      type: String,
      required: true,
    },
    effectiveCurrentDate: {
      type: String,
      required: true,
    },
  },
  emits: ['update:modelValue'],
  setup(props) {
    const currentDate = computed(() => new Date(props.effectiveCurrentDate))

    const showYTD = computed(() => {
      const currentYear = currentDate.value.getFullYear()
      const startOfYear = new Date(currentYear, 0, 1)
      return currentDate.value > startOfYear
    })

    // const ytdValue = computed(() => {
    //   return `YTD-${currentDate.value.getFullYear()}`
    // })

    return {
      showYTD,
      // ytdValue
    }
  },
}
</script>
