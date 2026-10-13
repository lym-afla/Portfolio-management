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
      :class="{ 'workspace-actions-row--measuring': measuring, 'workspace-actions-row--wrapped': wrapped }"
      :aria-hidden="measuring ? 'true' : undefined"
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
      <v-menu
        v-if="measuring || hiddenActions.length"
        :model-value="menuOpen"
        @update:model-value="onMenuUpdate"
      >
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
const wrapped = ref(false)
const directActions = computed(() => candidates.value.slice(0, visibleCount.value))
const hiddenActions = computed(() => candidates.value.slice(visibleCount.value))

const strip = ref<HTMLElement | null>(null)
const row = ref<HTMLElement | null>(null)
let observer: ResizeObserver | null = null
let lastObservedWidth = 0
let disposed = false
let fitting = false
let refitRequested = false
let fitGeneration = 0
// While the user's overflow menu is OPEN, fits are deferred: opening the
// overlay hides the body scrollbar, which changes this strip's width — a
// refit triggered by that would re-measure, empty the menu's items and
// close it mid-interaction. The fit runs when the menu closes.
const menuOpen = ref(false)

function onMenuUpdate(value: boolean) {
  menuOpen.value = value
}

// Fits are queued on the microtask queue, never on requestAnimationFrame:
// rAF does not fire in occluded windows, and a stalled fit would leave the
// row mid-measurement (candidates unmounted, menu closed) until a frame
// happened to be produced.
let fitQueued = false
function scheduleFit() {
  if (disposed) return
  if (menuOpen.value) {
    // A resize while the user's overflow menu is open closes the menu (the
    // refit would reshuffle its items mid-interaction) and runs right after
    // the close lands. Setting the model closes it; the update event is not
    // emitted for programmatic changes, so chain the fit here.
    menuOpen.value = false
    void nextTick().then(() => {
      if (!disposed) void fit()
    })
    return
  }
  // A resize observed while a fit is running must not be swallowed: queue a
  // refit that runs when the active one releases its measurement.
  if (fitting) {
    refitRequested = true
    return
  }
  if (fitQueued) return
  fitQueued = true
  void Promise.resolve().then(() => {
    fitQueued = false
    void fit()
  })
}

async function fit() {
  if (disposed || fitting || !strip.value || !row.value) return
  if (strip.value.clientWidth <= 0) return
  fitGeneration += 1
  const token = fitGeneration
  // Ownership: every await below can outlive this instance (unmount) or be
  // superseded by a newer fit — the continuation stops at the next check.
  const owned = () =>
    !disposed && token === fitGeneration && !!strip.value && !!row.value
  // The focused action's identity is captured BEFORE any DOM change: once
  // its button is unmounted, activeElement is already lost to <body>. Menu
  // items live in a teleported overlay, so containment alone is not enough —
  // a candidate id that belongs to this component counts as inside.
  const active = document.activeElement as HTMLElement | null
  const candidateIds = new Set(candidates.value.map((action) => action.id))
  const activeActionId =
    active?.closest?.('[data-action]')?.getAttribute('data-action') ?? null
  const focusInside =
    !!active &&
    (strip.value.contains(active) ||
      (activeActionId !== null && candidateIds.has(activeActionId)))
  fitting = true
  try {
    // Phase 1 — measure every candidate (and the activator) rendered.
    measuring.value = true
    visibleCount.value = candidates.value.length
    await nextTick()
    if (!owned()) return
    const gapWidth = parseFloat(
      getComputedStyle(row.value!).columnGap || '0'
    ) || 0
    const widths = [...row.value!.children].map((child) =>
      (child as HTMLElement).getBoundingClientRect().width
    )
    const fixedWidth = props.primary ? (widths.shift() ?? 0) : 0
    const menuWidth = widths.pop() ?? 0
    const availableWidth = strip.value.clientWidth
    let count = fitVisibleActions({
      availableWidth,
      itemWidths: widths,
      gap: gapWidth,
      fixedWidth,
      menuWidth,
    })
    // Degenerate row: even the primary action and the activator cannot share
    // one line. The wrap fallback is then permanent for this width — a
    // refit's "no overflow" is achieved BY the wrap, not by single-line
    // fitting, and must not reset it.
    const degenerate = fixedWidth + gapWidth + menuWidth > availableWidth
    measuring.value = false
    // Phase 2 — apply the estimate and correct against the real row. The
    // estimate can leave genuine overflow (sub-pixel rounding, font
    // metrics): each correction sheds ONE more action from the retained
    // count instead of restoring all candidates and recomputing the same
    // estimate. When even the primary action and the activator cannot share
    // one line, wrap — both controls stay visible instead of clipping.
    for (let attempt = 0; attempt <= candidates.value.length + 1; attempt += 1) {
      visibleCount.value = count
      await nextTick()
      if (!owned()) return
      if (!(row.value!.scrollWidth > row.value!.clientWidth + 1)) {
        if (!degenerate) wrapped.value = false
        restoreFocus(focusInside, activeActionId)
        return
      }
      if (count > 0) {
        count -= 1
        continue
      }
      wrapped.value = true
      await nextTick()
      if (!owned()) return
      restoreFocus(focusInside, activeActionId)
      return
    }
  } finally {
    fitting = false
    measuring.value = false
    if (refitRequested && !disposed) {
      refitRequested = false
      scheduleFit()
    }
  }
}

// The focused action returns to the same control where it still exists
// (either tier), otherwise to the More actions activator; if widening removed
// the activator entirely (everything direct), the last direct action takes
// focus so it never drops to <body>.
function restoreFocus(focusInside: boolean, activeActionId: string | null) {
  if (!focusInside || !row.value) return
  const sameAction = activeActionId
    ? [...row.value.querySelectorAll<HTMLElement>('[data-action]')].find(
        (element) => element.getAttribute('data-action') === activeActionId
      ) ?? null
    : null
  if (sameAction) {
    if (document.activeElement !== sameAction) sameAction.focus()
    return
  }
  const activator = row.value.querySelector<HTMLElement>(
    '[data-testid="workspace-actions-more"]'
  )
  if (activator) {
    if (document.activeElement !== activator) activator.focus()
    return
  }
  const direct = [
    ...row.value.querySelectorAll<HTMLElement>('[data-action]'),
  ]
  const fallback = direct[direct.length - 1] ?? null
  if (fallback && document.activeElement !== fallback) fallback.focus()
}

watch(candidates, () => {
  scheduleFit()
})

onMounted(() => {
  if (typeof ResizeObserver === 'undefined') return
  observer = new ResizeObserver((entries) => {
    // Only WIDTH changes drive the fit. The fit's own measuring toggle can
    // jitter the strip's box (the activator joins the row for the measure
    // pass) — honouring those self-induced events would refit forever.
    const width =
      entries[entries.length - 1]?.contentRect?.width ??
      strip.value?.clientWidth ??
      0
    if (Math.abs(width - lastObservedWidth) < 1) return
    lastObservedWidth = width
    scheduleFit()
  })
  observer.observe(strip.value!)
  scheduleFit()
})

onUnmounted(() => {
  disposed = true
  observer?.disconnect()
})

defineExpose({ visibleCount, wrapped, fit: scheduleFit })
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
/* Degenerate fallback: when even the primary action and the activator cannot
   share one line, wrap into stacked rows instead of clipping. The measuring
   phase always measures single-line. */
.workspace-actions-row--wrapped:not(.workspace-actions-row--measuring) {
  flex-wrap: wrap;
}

</style>
