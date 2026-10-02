<template>
  <div class="workspace-empty-state text-center pa-6">
    <h3 class="text-subtitle-1 font-weight-medium">{{ title }}</h3>
    <p class="text-body-2 text-medium-emphasis mt-1 mb-0">{{ description }}</p>
    <v-btn
      v-if="action"
      class="mt-3 workspace-touch-action"
      color="primary"
      variant="tonal"
      @click="emit('action', action.id)"
    >
      {{ action.label }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import type { WorkspaceAction } from '@/components/workspace/types'

defineProps<{
  title: string
  description: string
  action?: WorkspaceAction
}>()

const emit = defineEmits<{
  (e: 'action', id: string): void
}>()
</script>
