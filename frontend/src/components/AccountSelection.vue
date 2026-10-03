<template>
  <div class="account-selection">
    <v-card flat>
      <v-card-text class="pa-0">
        <div class="d-flex align-center">
          <v-btn
            aria-label="Previous account"
            @click="switchAccount(-1)"
            :disabled="
              context.isTransitioning || !context.isReady || !canSwitchLeft
            "
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-left</v-icon>
          </v-btn>
          <v-select
            :model-value="selectedAccount"
            :disabled="context.isTransitioning || !context.isReady"
            :loading="context.isTransitioning"
            :items="accountOptions"
            item-title="title"
            item-value="value"
            label="Account or Account group"
            density="comfortable"
            hide-details
            @update:model-value="handleAccountChange"
            class="account-select mx-2"
          >
            <template v-slot:selection>
              {{ selectedAccountLabel }}
            </template>
            <template v-slot:item="{ props, item }">
              <v-list-item
                v-if="item.raw.type === 'option'"
                v-bind="props"
                :title="null"
              >
                {{ item.raw.title }}
              </v-list-item>
              <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
              <v-list-subheader
                v-else-if="item.raw.type === 'header'"
                class="custom-subheader"
              >
                {{ item.raw.title }}
              </v-list-subheader>
            </template>
          </v-select>
          <v-btn
            aria-label="Next account"
            @click="switchAccount(1)"
            :disabled="
              context.isTransitioning || !context.isReady || !canSwitchRight
            "
            class="arrow-btn"
            variant="outlined"
          >
            <v-icon>mdi-chevron-right</v-icon>
          </v-btn>
        </div>
        <v-alert
          v-if="!intentOnly && context.transitionError"
          type="error"
          role="alert"
          >{{ context.transitionError.message }}</v-alert
        >
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { committedAccountLabel, formatAccountChoices } from '@/utils/accountUtils'

const props = defineProps({ intentOnly: Boolean })
const emit = defineEmits(['request-change'])
const context = usePortfolioContextStore()
const accountOptions = computed(() =>
  formatAccountChoices(context.accountOptions)
)
// The committed selection may legitimately be absent from the loaded options
// (empty or not-yet-loaded choices, a removed account). Rendering the raw
// model value would show Vuetify's [object Object]; the shared label helper
// renders the matching option title or the safe All accounts/Unavailable
// fallbacks without inventing an option or firing any request.
const selectedAccountLabel = computed(() =>
  committedAccountLabel(context.accountOptions, context.committed.accountSelection)
)
const selectedAccount = computed(() => {
  const committed = context.committed.accountSelection
  return (
    accountOptions.value.find(
      (option) =>
        option.type === 'option' &&
        option.value.type === committed.type &&
        option.value.id === committed.id
    )?.value || committed
  )
})
const currentIndex = computed(() =>
  accountOptions.value.findIndex(
    (option) =>
      option.type === 'option' &&
      option.value.type === selectedAccount.value.type &&
      option.value.id === selectedAccount.value.id
  )
)
const canSwitchLeft = computed(
  () =>
    currentIndex.value > 0 &&
    accountOptions.value
      .slice(0, currentIndex.value)
      .some((option) => option.type === 'option')
)
const canSwitchRight = computed(() =>
  accountOptions.value
    .slice(currentIndex.value + 1)
    .some((option) => option.type === 'option')
)
async function handleAccountChange(value) {
  if (!value || context.isTransitioning || !context.isReady) return
  if (props.intentOnly) {
    emit('request-change', {
      accountSelection: { type: value.type, id: value.id },
    })
    return
  }
  try {
    await context.changeContext({
      accountSelection: { type: value.type, id: value.id },
    })
  } catch {
    /* The context store exposes the actual error and retains confirmed values. */
  }
}
function switchAccount(direction) {
  if (context.isTransitioning || !context.isReady) return
  let index = currentIndex.value + direction
  while (index >= 0 && index < accountOptions.value.length) {
    const option = accountOptions.value[index]
    if (option.type === 'option') {
      handleAccountChange(option.value)
      return
    }
    index += direction
  }
}
</script>

<style scoped>
.account-selection {
  --select-height: 56px;
}

.custom-subheader {
  font-weight: bold;
  font-size: 1.1em;
  color: rgb(var(--v-theme-on-surface));
  padding-top: 12px;
  padding-bottom: 12px;
  background-color: #f5f5f5;
}

.arrow-btn {
  width: var(--select-height);
  height: var(--select-height);
  min-width: 0;
  padding: 0;
}

.account-select {
  min-width: 0;
  flex-grow: 1;
}

.v-card-text {
  padding: 8px 0;
}

:deep(.v-field__input) {
  min-height: var(--select-height);
}

:deep(.v-field__outline) {
  --v-field-border-width: 1px;
}
@media (max-width: 599px) {
  .arrow-btn {
    display: none;
  }
  .account-select {
    margin: 0 !important;
  }
}
</style>
