<template>
  <!-- Layout/intent component only: it renders labelled query controls plus
       filter/column/action slots and emits one update:query intent per
       change. Debouncing, fetching and money formatting stay with the
       parent's existing setters — never a second query pipeline here. -->
  <div class="workspace-table-toolbar">
    <div v-if="$slots.filters" class="workspace-table-toolbar__filters">
      <slot name="filters" />
    </div>
    <v-text-field
      :model-value="query.search"
      :aria-label="searchLabel"
      :label="searchLabel"
      :placeholder="searchPlaceholder"
      class="workspace-table-toolbar__search"
      prepend-inner-icon="mdi-magnify"
      single-line
      hide-details
      clearable
      density="compact"
      variant="outlined"
      bg-color="surface"
      @update:model-value="emitSearch"
      @click:clear="emitSearch('')"
    />
    <div v-if="$slots.columns" class="workspace-table-toolbar__columns">
      <slot name="columns" />
    </div>
    <div v-if="$slots.actions" class="workspace-table-toolbar__actions">
      <slot name="actions" />
    </div>
    <v-select
      :model-value="query.itemsPerPage"
      :items="[...rowsPerPageOptions]"
      label="Rows per page"
      class="workspace-table-toolbar__rows"
      density="compact"
      variant="outlined"
      hide-details
      bg-color="surface"
      @update:model-value="emitItemsPerPage"
    />
  </div>
</template>

<script setup lang="ts">
import type { TableQueryView } from '@/components/workspace/types'

const props = defineProps<{
  query: TableQueryView
  searchLabel: string
  searchPlaceholder?: string
  rowsPerPageOptions: readonly number[]
}>()

const emit = defineEmits<{
  (e: 'update:query', patch: Partial<TableQueryView>): void
}>()

const emitSearch = (value: string | null) => {
  emit('update:query', { search: value ?? '' })
}

const emitItemsPerPage = (value: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return
  emit('update:query', { itemsPerPage: Number(value) })
}
</script>

<style scoped>
/* Wrapping control strip that stays OUTSIDE the table's horizontal scroll
   region. Vuetify's v-toolbar boxes content into a fixed 64px inline height
   with overflow hidden (the D3 clipping lesson), so this toolbar is a plain
   wrapping flex box that grows with its rows instead. */
.workspace-table-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px 12px;
}

.workspace-table-toolbar__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.workspace-table-toolbar__search {
  flex: 1 1 220px;
  min-width: 180px;
  max-width: 420px;
}

.workspace-table-toolbar__columns,
.workspace-table-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.workspace-table-toolbar__rows {
  flex: 0 1 auto;
  min-width: 150px;
  max-width: 200px;
  margin-left: auto;
}

@media (max-width: 599px) {
  .workspace-table-toolbar__rows {
    margin-left: 0;
  }
}
</style>
