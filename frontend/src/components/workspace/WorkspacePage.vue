<script setup lang="ts">
import { inject, onMounted, onUnmounted } from 'vue'
import { workspaceDefaults } from '@/theme/defaults'
import { workspaceHeadingKey } from './types'

defineProps<{ title: string; description?: string }>()
const registerHeading = inject(workspaceHeadingKey, undefined)
let releaseHeading: (() => void) | undefined
onMounted(() => { releaseHeading = registerHeading?.() })
onUnmounted(() => releaseHeading?.())
</script>

<template>
  <v-defaults-provider :defaults="workspaceDefaults">
    <div class="workspace-ui workspace-page">
      <header class="workspace-page__header">
        <div>
          <h1>{{ title }}</h1>
          <p v-if="description" class="workspace-meta">{{ description }}</p>
        </div>
        <div v-if="$slots.actions" class="workspace-actions"><slot name="actions" /></div>
      </header>
      <div v-if="$slots.context" class="workspace-page__context"><slot name="context" /></div>
      <slot />
    </div>
  </v-defaults-provider>
</template>
