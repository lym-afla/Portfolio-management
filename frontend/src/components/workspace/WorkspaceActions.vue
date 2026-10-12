<template>
  <!-- Presentation-only action hierarchy: primary, secondary and overflow
       tiers emit exact action ids; the parent owns handlers and dialogs.
       The candidate actions (secondary + overflow, in order) are shown
       directly whenever the measured row width permits; the remaining suffix
       moves into the "More actions" menu on narrower layouts. Each action
       has exactly one active instance, and every instance emits the same
       unchanged action id. -->
  <div ref="strip" class="workspace-actions-strip">
    <div
      ref="row"
      class="workspace-actions-row d-flex align-center ga-2"
      :class="{ 'workspace-actions-row--measuring': measuring }"
    >
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
        v-for="action in directActions"
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
      <v-menu v-if="measuring || hiddenActions.length">
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            icon="mdi-dots-horizontal"
            variant="text"
            aria-label="More actions"
            class="workspace-touch-action"
            data-testid="workspace-actions-more"
          />
        </template>
        <v-list density="compact">
          <v-list-item
            v-for="action in hiddenActions"
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
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import type { WorkspaceAction } from '@/components/workspace/types'
import { fitVisibleActions } from './fitActions'

const props = defineProps<{
  primary?: WorkspaceAction
  secondary: readonly WorkspaceAction[]
  overflow: readonly WorkspaceAction[]
}>()

const emit = defineEmits<{
  (e: 'action', id: string): void
}>()

const candidates = computed(() => [...props.secondary, ...props.overflow])
// Everything direct by default — the incumbent presentation. Fitting only
// runs with real layout (a measured container); without one (unit jsdom)
// nothing is hidden.
const visibleCount = ref(candidates.value.length)
const measuring = ref(false)
const directActions = computed(() => candidates.value.slice(0, visibleCount.value))
const hiddenActions = computed(() => candidates.value.slice(visibleCount.value))

const strip = ref<HTMLElement | null>(null)
const row = ref<HTMLElement | null>(null)
let frame = 0
let observer: ResizeObserver | null = null
let fitting = false

function scheduleFit() {
  if (!frame) frame = requestAnimationFrame(() => {
    frame = 0
    void fit()
  })
}

async function fit() {
  if (fitting || !strip.value || !row.value) return
  if (strip.value.clientWidth <= 0) return
  fitting = true
  try {
    for (let attempt = 0; attempt <= candidates.value.length; attempt += 1) {
      // Render every candidate (and the activator) so each real width can be
      // measured, then keep the largest ordered prefix that fits.
      measuring.value = true
      visibleCount.value = candidates.value.length
      await nextTick()
      await nextFrame()
      const gapWidth = parseFloat(
        getComputedStyle(row.value!).columnGap || '0'
      ) || 0
      const widths = [...row.value!.children].map((child) =>
        (child as HTMLElement).getBoundingClientRect().width
      )
      const fixedWidth = props.primary ? (widths.shift() ?? 0) : 0
      const menuWidth = widths.pop() ?? 0
      const count = fitVisibleActions({
        availableWidth: strip.value.clientWidth,
        itemWidths: widths,
        gap: gapWidth,
        fixedWidth,
        menuWidth,
      })
      measuring.value = false
      visibleCount.value = count
      await nextTick()
      await nextFrame()
      // Verification pass: if the fitted row still overflows (sub-pixel or
      // font differences), shed one more action; bounded by the candidate
      // count.
      const overflowing =
        row.value!.scrollWidth > row.value!.clientWidth + 1
      if (!overflowing) {
        restoreFocusIfHidden()
        return
      }
    }
  } finally {
    fitting = false
    measuring.value = false
  }
}

// Narrowing between direct and menu must not strand keyboard focus on an
// unmounted button: when the focused action moved into the menu, focus the
// activator.
function restoreFocusIfHidden() {
  const active = document.activeElement as HTMLElement | null
  if (!active || active.isConnected) return
  if (!active.matches('[data-action]')) return
  const activator = row.value?.querySelector<HTMLElement>(
    '[data-testid="workspace-actions-more"]'
  )
  activator?.focus()
}

function nextFrame() {
  return new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  )
}

watch(candidates, () => {
  visibleCount.value = candidates.value.length
  scheduleFit()
})

onMounted(() => {
  if (typeof ResizeObserver === 'undefined') return
  observer = new ResizeObserver(scheduleFit)
  observer.observe(strip.value!)
  scheduleFit()
})

onUnmounted(() => {
  if (frame) cancelAnimationFrame(frame)
  observer?.disconnect()
})

defineExpose({ visibleCount, fit: scheduleFit })
</script>

<style scoped>
/* The strip owns the measured width; the row never wraps, because wrapping
   would silently push actions out of the measured single-line budget. The
   fit loop keeps the row within the strip at every width. */
.workspace-actions-strip {
  width: 100%;
  min-width: 0;
}
.workspace-actions-row {
  flex-wrap: nowrap;
  min-width: 0;
}
</style>
