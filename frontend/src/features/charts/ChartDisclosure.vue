<template>
  <!-- Phase C: exact-value tables default to collapsed disclosures behind a
       labelled button. The toggle is a native button (keyboard Enter/Space
       for free) with aria-expanded; the content renders only while expanded. -->
  <div class="chart-disclosure">
    <button
      type="button"
      class="chart-disclosure__toggle"
      :data-testid="testId"
      :aria-expanded="open ? 'true' : 'false'"
      @click="open = !open"
    >
      {{ open ? hideLabel : showLabel }}
    </button>
    <div v-if="open" class="chart-disclosure__content">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  showLabel: string
  hideLabel: string
  testId: string
}>()

const open = ref(false)
</script>

<style scoped>
.chart-disclosure {
  min-width: 0;
}

.chart-disclosure__toggle {
  border: 1px solid rgba(23, 43, 77, 0.24);
  background: #fff;
  border-radius: 4px;
  min-height: 36px;
  padding: 4px 12px;
  cursor: pointer;
  font-size: 0.875rem;
  color: #172b4d;
}

.chart-disclosure__toggle:focus-visible {
  outline: 2px solid #0f4c81;
  outline-offset: 2px;
}

.chart-disclosure__content {
  min-width: 0;
}
</style>
