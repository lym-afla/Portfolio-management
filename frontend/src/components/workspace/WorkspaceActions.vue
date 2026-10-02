<template>
  <!-- Presentation-only action hierarchy: primary, secondary and overflow
       tiers emit exact action ids; the parent owns handlers and dialogs. -->
  <div class="workspace-actions d-flex flex-wrap align-center ga-2">
    <v-btn
      v-if="primary"
      color="primary"
      :prepend-icon="primary.icon"
      :disabled="primary.disabled"
      :loading="primary.loading"
      :data-action="primary.id"
      class="workspace-touch-action"
      @click="emit('action', primary.id)"
    >
      {{ primary.label }}
    </v-btn>
    <v-btn
      v-for="action in secondary"
      :key="action.id"
      color="secondary"
      variant="tonal"
      :prepend-icon="action.icon"
      :disabled="action.disabled"
      :loading="action.loading"
      :data-action="action.id"
      class="workspace-touch-action"
      @click="emit('action', action.id)"
    >
      {{ action.label }}
    </v-btn>
    <v-menu v-if="overflow.length">
      <template #activator="{ props: menuProps }">
        <v-btn
          v-bind="menuProps"
          icon="mdi-dots-horizontal"
          variant="text"
          aria-label="More actions"
          class="workspace-touch-action"
        />
      </template>
      <v-list density="compact">
        <v-list-item
          v-for="action in overflow"
          :key="action.id"
          :prepend-icon="action.icon"
          :disabled="action.disabled"
          :data-action="action.id"
          @click="emit('action', action.id)"
        >
          {{ action.label }}
        </v-list-item>
      </v-list>
    </v-menu>
  </div>
</template>

<script setup lang="ts">
import type { WorkspaceAction } from '@/components/workspace/types'

defineProps<{
  primary?: WorkspaceAction
  secondary: readonly WorkspaceAction[]
  overflow: readonly WorkspaceAction[]
}>()

const emit = defineEmits<{
  (e: 'action', id: string): void
}>()
</script>
