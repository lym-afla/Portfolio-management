<script setup lang="ts">
import type { ContextIntent, WorkspaceContextView } from './types'
defineProps<{ view: WorkspaceContextView }>()
defineEmits<{
  'request-change': [intent: ContextIntent]
  'open-preferences': []
}>()
</script>
<template>
  <section
    class="workspace-context"
    aria-label="Portfolio context"
    :aria-busy="view.isTransitioning"
  >
    <!-- The controls slot IS the committed-context display (account, valuation
         date, currency); repeating it as summary text duplicated the header.
         Only the display-preferences action and pending/error feedback live
         beside it. -->
    <div class="workspace-context__bar">
      <slot name="controls" />
      <button
        type="button"
        class="workspace-context__preferences"
        aria-label="Display preferences"
        :disabled="!view.isReady || view.isTransitioning"
        @click="$emit('open-preferences')"
      >
        Display preferences
      </button>
    </div>
    <p v-if="view.isTransitioning" role="status" aria-live="polite">
      {{
        view.pendingLabel
          ? `Updating to ${view.pendingLabel}…`
          : 'Updating portfolio context…'
      }}
    </p>
    <p v-if="view.errorMessage" role="alert">{{ view.errorMessage }}</p>
  </section>
</template>
<style scoped>
.workspace-context {
  width: 100%;
}
.workspace-context__bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  /* Room for the outlined fields' floated labels, which rise above the
     field boxes. */
  padding-top: 10px;
}
.workspace-context__preferences {
  margin-left: auto;
  min-height: 44px;
  padding: 4px 8px;
  color: rgb(var(--v-theme-primary));
  border-radius: 4px;
}
.workspace-context__preferences:focus-visible {
  outline: 2px solid rgb(var(--v-theme-focus));
  outline-offset: 2px;
}
.workspace-context__preferences:disabled {
  opacity: 0.5;
}
.workspace-context p {
  margin: 8px 0 0;
}
@media (max-width: 599px) {
  .workspace-context__preferences {
    margin-left: 0;
  }
}
</style>
