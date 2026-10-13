<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import { workspaceNavigation } from './workspace/navigation'
const { mdAndUp } = useDisplay()
const route = useRoute()
const router = useRouter()
const opened = ref(false)
const trigger = ref<{ $el: HTMLElement } | HTMLElement | null>(null)
const drawer = computed({
  get: () => mdAndUp.value || opened.value,
  set: (value: boolean) => {
    opened.value = value
  },
})
// Compact desktop rail: Vuetify's expand-on-hover keeps the registered
// layout size at the rail width, so expansion overlays the page instead of
// reflowing it. The pointer path is Vuetify's own; keyboard focus drives the
// same public mouseenter/mouseleave contract, and the rail collapses only
// after pointer AND focus have both left.
const drawerRef = ref<{ $el: HTMLElement } | null>(null)
const pointerInside = ref(false)
const focusInside = ref(false)
const navExpanded = computed(
  () => !mdAndUp.value || pointerInside.value || focusInside.value
)
let syntheticDispatch = false
// Vuetify's drawer exposes only its own internals (no $el), so fall back to
// the stable element id for the synthetic hover events.
function drawerElement(): HTMLElement | null {
  const ref = drawerRef.value as { $el?: HTMLElement } | null
  if (ref && ref.$el instanceof HTMLElement) return ref.$el
  return document.getElementById('workspace-navigation')
}
function dispatchHover(enter: boolean) {
  const el = drawerElement()
  if (!el) return
  syntheticDispatch = true
  el.dispatchEvent(new MouseEvent(enter ? 'mouseenter' : 'mouseleave'))
  syntheticDispatch = false
}
function onPointerEnter() {
  if (syntheticDispatch || !mdAndUp.value) return
  pointerInside.value = true
}
function onPointerLeave() {
  if (syntheticDispatch || !mdAndUp.value) return
  pointerInside.value = false
  if (focusInside.value) dispatchHover(true)
}
function onFocusIn(event: FocusEvent) {
  if (!mdAndUp.value) return
  const el = drawerElement()
  if (el && event.relatedTarget instanceof Node && el.contains(event.relatedTarget)) return
  focusInside.value = true
  if (!pointerInside.value) dispatchHover(true)
}
function onFocusOut(event: FocusEvent) {
  if (!mdAndUp.value) return
  const el = drawerElement()
  if (el && event.relatedTarget instanceof Node && el.contains(event.relatedTarget)) return
  focusInside.value = false
  if (!pointerInside.value) dispatchHover(false)
}
async function closeNavigation() {
  if (mdAndUp.value) return
  opened.value = false
  await nextTick()
  const element =
    trigger.value &&
    ('$el' in trigger.value ? trigger.value.$el : trigger.value)
  element?.focus()
}
async function navigate(path: string) {
  await router.push(path)
  await closeNavigation()
}
function onEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && opened.value && !mdAndUp.value)
    void closeNavigation()
}
onMounted(() => document.addEventListener('keydown', onEscape))
onUnmounted(() => document.removeEventListener('keydown', onEscape))
watch(mdAndUp, () => {
  opened.value = false
  pointerInside.value = false
  focusInside.value = false
})
watch(opened, (value, previous) => {
  if (!value && previous && !mdAndUp.value) void closeNavigation()
})
function active(path: string) {
  return path === '/profile'
    ? route.path.startsWith('/profile')
    : route.path === path
}
defineExpose({ navExpanded })
</script>
<template>
  <v-btn
    v-if="!mdAndUp"
    ref="trigger"
    class="workspace-navigation-trigger"
    icon
    variant="text"
    aria-label="Open navigation"
    :aria-expanded="opened"
    aria-controls="workspace-navigation"
    @click="opened = true"
    ><v-icon>mdi-menu</v-icon></v-btn
  >
  <v-navigation-drawer
    v-model="drawer"
    ref="drawerRef"
    id="workspace-navigation"
    :rail="mdAndUp"
    :permanent="mdAndUp"
    :temporary="!mdAndUp"
    :expand-on-hover="mdAndUp"
    rail-width="72"
    width="224"
    aria-label="Main navigation"
    @keydown.esc="closeNavigation"
    @mouseenter="onPointerEnter"
    @mouseleave="onPointerLeave"
    @focusin="onFocusIn"
    @focusout="onFocusOut"
  >
    <v-list density="compact" nav>
      <template v-for="(item, index) in workspaceNavigation" :key="item.to">
        <v-list-subheader v-if="index === 0">Portfolio</v-list-subheader>
        <v-list-subheader v-if="item.to === '/open-positions'"
          >Positions</v-list-subheader
        >
        <v-divider
          v-if="
            item.section !== workspaceNavigation[index - 1]?.section &&
            index > 0
          "
          class="my-2"
        />
        <v-list-subheader
          v-if="
            item.section === 'data' &&
            workspaceNavigation[index - 1]?.section !== 'data'
          "
          >Data</v-list-subheader
        >
        <v-list-subheader v-if="item.section === 'personal'"
          >Personal</v-list-subheader
        >
        <v-list-item
          :to="item.to"
          :title="item.label"
          :aria-label="item.label"
          :prepend-icon="item.icon"
          :active="active(item.to)"
          :aria-current="active(item.to) ? 'page' : undefined"
          @click.prevent="navigate(item.to)"
        />
      </template>
    </v-list>
  </v-navigation-drawer>
</template>
<style scoped>
.workspace-navigation-trigger {
  position: fixed;
  top: 8px;
  left: 8px;
  z-index: 1010;
}
/* Rail items keep a 44px+ hit area while the collapsed rail stays narrow;
   the list itself never scrolls horizontally when the rail expands. */
.v-navigation-drawer :deep(.v-list-item) {
  min-height: 44px;
}
/* Collapsed rail: section headers stay in the accessibility tree — the
   element structure is identical expanded and collapsed, so the section
   names never appear or vanish between interactions — but compress to quiet
   separators so the compact rail shows icons only. */
.v-navigation-drawer--rail:not(.v-navigation-drawer--is-hovering)
  :deep(.v-list-subheader) {
  font-size: 0;
  color: transparent;
  min-height: 0;
  height: 10px;
  padding: 0;
  overflow: hidden;
}
.v-navigation-drawer--rail:not(.v-navigation-drawer--is-hovering)
  :deep(.v-divider) {
  margin: 2px 0;
}
</style>
