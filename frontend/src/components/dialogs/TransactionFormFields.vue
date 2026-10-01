<template>
  <!-- Server-driven form fields, unchanged rendering contract (labels,
       errors, Yup wiring, bond % suffix live in the parent dialogs). -->
  <template v-for="field in fields" :key="field.name">
    <v-text-field
      v-if="field.type === 'datepicker'"
      :model-value="valueFor(field.name)"
      :label="field.label"
      type="date"
      :required="field.required"
      :error-messages="errorFor(field.name)"
      @update:model-value="(value) => update(field.name, value)"
    />

    <v-autocomplete
      v-else-if="field.type === 'select'"
      :model-value="valueFor(field.name)"
      :items="field.choices"
      item-title="text"
      item-value="value"
      :label="field.label"
      :required="field.required"
      :error-messages="errorFor(field.name)"
      clearable
      @update:model-value="(value) => update(field.name, value)"
    >
      <template v-slot:selection="{ item }">
        {{ item.raw ? item.raw.text : '' }}
      </template>
    </v-autocomplete>

    <v-text-field
      v-else-if="field.type === 'number'"
      :model-value="valueFor(field.name)"
      :label="field.label"
      type="number"
      :step="['split_from', 'split_to'].includes(field.name) ? '1' : '0.01'"
      :required="field.required"
      :error-messages="errorFor(field.name)"
      :hint="field.helper_text"
      :persistent-hint="!!field.helper_text"
      :suffix="field.name === 'price' && bondPrice ? '%' : ''"
      @update:model-value="(value) => update(field.name, value)"
    />

    <v-textarea
      v-else-if="field.type === 'textarea'"
      :model-value="valueFor(field.name)"
      :label="field.label"
      :required="field.required"
      :error-messages="errorFor(field.name)"
      @update:model-value="(value) => update(field.name, value)"
    />
  </template>
</template>

<script setup>
defineProps({
  fields: { type: Array, required: true },
  valueFor: { type: Function, required: true },
  errorFor: { type: Function, required: true },
  update: { type: Function, required: true },
  bondPrice: { type: Boolean, default: false },
})
</script>
