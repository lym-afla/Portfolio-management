<template>
  <!-- Presentation-only destructive confirmation. The parent owns detail
       loading, API calls and the immutable selected identity; this dialog
       never invents or retargets the subject. -->
  <v-dialog
    :model-value="modelValue"
    max-width="480px"
    :persistent="busy"
    aria-labelledby="confirm-action-title"
    aria-describedby="confirm-action-details"
    @update:model-value="onDialogChange"
    @after-leave="restoreFocus"
  >
    <v-card>
      <v-card-title id="confirm-action-title" class="text-h6">
        {{ safeSubject.title }}
      </v-card-title>
      <v-card-text>
        <p v-if="detailsPending" class="text-body-2 mb-0">
          Loading transaction details…
        </p>
        <dl v-else id="confirm-action-details" class="confirm-details">
          <template v-for="(detail, index) in safeSubject.details" :key="`${detail.label}-${index}`">
            <dt class="text-body-2 text-medium-emphasis">{{ detail.label }}</dt>
            <dd class="text-body-2">{{ detail.value }}</dd>
          </template>
        </dl>
        <v-alert v-if="error" type="error" density="compact" class="mt-3" role="alert">
          {{ error }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          ref="cancelRef"
          data-testid="confirm-cancel"
          :disabled="busy"
          @click="onDialogChange(false)"
        >
          Cancel
        </v-btn>
        <v-btn
          data-testid="confirm-confirm"
          color="error"
          variant="tonal"
          :disabled="busy || detailsPending || confirmDisabled"
          :loading="busy || detailsPending"
          @click="confirmOnce"
        >
          {{ safeSubject.confirmLabel }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ConfirmationSubject } from '@/components/workspace/types'

const props = withDefaults(defineProps<{
  modelValue: boolean
  subject: ConfirmationSubject
  busy: boolean
  error: string | null
  /** Detail loading by the parent keeps confirmation disabled but cancellable. */
  detailsPending?: boolean
  /** Detail loading failed: stay cancellable but never confirmable. */
  confirmDisabled?: boolean
}>(), {
  detailsPending: false,
  confirmDisabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()

// Parents may drop the subject as the dialog closes while the overlay is
// still leaving; never render a null subject.
const safeSubject = computed<ConfirmationSubject>(() =>
  props.subject ?? { title: '', confirmLabel: '', details: [] },
)

const cancelRef = ref<{ $el: HTMLElement } | null>(null)
let previouslyFocused: HTMLElement | null = null

// Destructive default: initial focus lands on Cancel, never on the
// confirming action. Focus returns to the invoking control on close —
// both on the model flip (overlays linger hidden during the leave
// transition) and on after-leave in browsers that complete it.
watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
      await nextTick()
      const cancelEl = cancelRef.value?.$el as HTMLElement | undefined
      if (cancelEl) {
        const focusTarget = (cancelEl.querySelector('button, [tabindex]') as HTMLElement | null) ?? cancelEl
        focusTarget.focus()
      }
    } else {
      await nextTick()
      restoreFocus()
    }
  },
  { immediate: true },
)

const onDialogChange = (value: boolean) => {
  if (props.busy) return
  emit('update:modelValue', value)
}

const confirmOnce = () => {
  if (props.busy || props.detailsPending || props.confirmDisabled) return
  emit('confirm')
}

// Focus returns to the invoking control after the dialog leaves; if that
// element is gone (e.g. its row was deleted) the parent applies a fallback.
const restoreFocus = () => {
  if (previouslyFocused?.isConnected) previouslyFocused.focus()
  previouslyFocused = null
}
</script>

<style scoped>
.confirm-details {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 16px;
  row-gap: 4px;
  margin: 0;
}
.confirm-details dt {
  font-weight: 500;
}
.confirm-details dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
</style>
