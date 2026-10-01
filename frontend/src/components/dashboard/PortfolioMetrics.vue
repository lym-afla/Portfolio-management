<template>
  <section class="portfolio-metrics-section" aria-label="Portfolio values">
    <p class="workspace-meta" data-testid="portfolio-context-label">{{ contextLabel }}</p>
    <dl class="portfolio-metrics">
      <div
        v-for="metric in metrics"
        :key="metric.id"
        :data-metric="metric.id"
        :class="{ 'portfolio-metrics__primary': metric.id === 'nav' }"
      >
        <dt>{{ metric.label }}</dt>
        <dd class="workspace-number">
          {{ metric.value ?? 'N/R' }}<span v-if="metric.unitLabel" class="portfolio-metrics__unit">{{ metric.unitLabel }}</span>
        </dd>
        <p v-if="metric.explanation" class="workspace-meta">{{ metric.explanation }}</p>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import type { MetricDisplay } from '@/components/workspace/types'

// Display-only: renders the validated, already-formatted summary strings.
// `null` is the only unrenderable value and uses the established N/R marker.
defineProps<{ metrics: readonly MetricDisplay[]; contextLabel: string }>()
</script>

<style scoped>
.portfolio-metrics-section {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.portfolio-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
  margin: 0;
}

.portfolio-metrics > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.portfolio-metrics dt {
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-text-secondary));
}

.portfolio-metrics dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  text-align: right;
  overflow-wrap: anywhere;
}

.portfolio-metrics__primary {
  grid-column: 1 / -1;
}

.portfolio-metrics__primary dt {
  font-size: 0.875rem;
}

.portfolio-metrics__primary dd {
  font-size: var(--workspace-metric, 2.25rem);
  line-height: 1.2;
  font-weight: 650;
}

.portfolio-metrics__unit {
  margin-left: 4px;
  font-size: 0.75em;
  color: rgb(var(--v-theme-text-secondary));
}

@media (min-width: 960px) {
  .portfolio-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
