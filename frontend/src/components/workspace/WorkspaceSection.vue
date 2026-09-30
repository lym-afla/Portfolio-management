<script setup lang="ts">
defineProps<{ headingId: string; title: string; description?: string }>()
</script>

<template>
  <section :aria-labelledby="headingId" class="workspace-section">
    <header class="workspace-section__header">
      <div>
        <h2 :id="headingId">{{ title }}</h2>
        <p v-if="description" class="workspace-meta">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="workspace-actions"><slot name="actions" /></div>
    </header>
    <slot />
  </section>
</template>
