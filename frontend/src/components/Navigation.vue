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
})
watch(opened, (value, previous) => {
  if (!value && previous && !mdAndUp.value) void closeNavigation()
})
function active(path: string) {
  return path === '/profile'
    ? route.path.startsWith('/profile')
    : route.path === path
}
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
    id="workspace-navigation"
    :rail="false"
    :permanent="mdAndUp"
    :temporary="!mdAndUp"
    width="224"
    aria-label="Main navigation"
    @keydown.esc="closeNavigation"
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
</style>
