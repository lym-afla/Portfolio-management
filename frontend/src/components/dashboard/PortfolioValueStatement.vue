<template>
  <section
    class="statement-section"
    aria-label="Portfolio value statement"
    data-testid="portfolio-statement-section"
  >
    <p class="workspace-meta" data-testid="portfolio-context-label">{{ contextLabel }}</p>
    <div class="statement-columns">
      <div class="statement">
        <dl class="statement-rows" data-testid="statement-capital">
          <div class="statement-row">
            <dt>Invested</dt>
            <dd class="workspace-number">{{ cellText(statement.capital.invested) }}<template v-if="flag(statement.capital.invested)"><span class="amount-flag" :title="statement.capital.invested.reason"> {{ flag(statement.capital.invested) }}</span></template></dd>
          </div>
          <div class="statement-row">
            <dt>Cash out</dt>
            <dd class="workspace-number">{{ cellText(statement.capital.cashOut) }}<template v-if="flag(statement.capital.cashOut)"><span class="amount-flag" :title="statement.capital.cashOut.reason"> {{ flag(statement.capital.cashOut) }}</span></template></dd>
          </div>
          <div class="statement-row subtotal">
            <dt>Net invested capital</dt>
            <dd class="workspace-number">{{ cellText(statement.capital.netInvestedCapital) }}<template v-if="flag(statement.capital.netInvestedCapital)"><span class="amount-flag" :title="statement.capital.netInvestedCapital.reason"> {{ flag(statement.capital.netInvestedCapital) }}</span></template></dd>
          </div>
          <div class="statement-row subtotal">
            <dt>Net result</dt>
            <dd class="workspace-number net-result-cell">
              <span>{{ cellText(statement.netResult.controlTotal) }}<template v-if="flag(statement.netResult.controlTotal)"><span class="amount-flag" :title="statement.netResult.controlTotal.reason"> {{ flag(statement.netResult.controlTotal) }}</span></template></span>
              <button
                type="button"
                class="statement-toggle"
                :aria-expanded="expanded ? 'true' : 'false'"
                aria-controls="net-result-breakdown"
                data-testid="breakdown-toggle"
                @click="expanded = !expanded"
              >
                <v-icon :icon="expanded ? mdiChevronUp : mdiChevronDown" size="small" aria-hidden="true" />
                <span class="sr-only">{{ expanded ? 'Hide' : 'Show' }} net result breakdown</span>
              </button>
            </dd>
          </div>
        </dl>
        <div
          id="net-result-breakdown"
          v-show="expanded"
          class="breakdown"
          data-testid="net-result-breakdown"
        >
          <dl class="statement-rows">
            <div v-for="row in breakdownRows" :key="row.key" class="statement-row breakdown-row">
              <dt>{{ row.label }}</dt>
              <dd class="workspace-number">{{ row.display }}<template v-if="row.flag"><span class="amount-flag" :title="row.flagTitle"> {{ row.flag }}</span></template></dd>
            </div>
          </dl>
          <p class="workspace-meta breakdown-help">
            Price gains exclude FX; FX shown separately.
          </p>
          <p
            v-if="displayRoundingNote"
            class="workspace-meta"
            data-testid="display-rounding-note"
          >
            {{ displayRoundingNote }}
          </p>
        </div>
        <p
          v-if="statusNotice"
          class="statement-status"
          data-testid="statement-status"
          role="status"
        >
          {{ statusNotice }}
        </p>
        <div class="statement-row total-row">
          <dt>Total NAV</dt>
          <dd class="workspace-number">{{ cellText(statement.netResult.nav) }}<template v-if="flag(statement.netResult.nav)"><span class="amount-flag" :title="statement.netResult.nav.reason"> {{ flag(statement.netResult.nav) }}</span></template></dd>
        </div>
      </div>
      <div class="returns" aria-label="Returns">
        <div class="returns-grid">
          <div class="returns-cell">
            <p class="returns-label">Total return</p>
            <p class="returns-value" data-testid="total-return">{{ statement.returns.totalReturn.display }}<template v-if="returnFlag(statement.returns.totalReturn)"><span class="amount-flag" :title="statement.returns.totalReturn.reason"> {{ returnFlag(statement.returns.totalReturn) }}</span></template></p>
            <p class="workspace-meta">Since inception</p>
          </div>
          <div class="returns-cell">
            <p class="returns-label">IRR since inception</p>
            <p class="returns-value" data-testid="irr-since-inception">{{ statement.returns.irr.display }}<template v-if="returnFlag(statement.returns.irr)"><span class="amount-flag" :title="statement.returns.irr.reason"> {{ returnFlag(statement.returns.irr) }}</span></template></p>
            <p class="workspace-meta" aria-hidden="true">&nbsp;</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { mdiChevronDown, mdiChevronUp } from '@mdi/js'
import type {
  ReconciledStatement,
  StatementAmount,
  StatementReturn,
} from '@/services/api'
import {
  displayRoundingAdjustment,
  formatScaledInteger,
  parseDisplayScaled,
} from '@/components/dashboard/statementDisplay'

// Display-only: renders the backend-formatted statement strings verbatim.
// No financial arithmetic happens here — the only computation is the
// display-rounding cross-check over already-rounded display strings.
const props = defineProps<{
  statement: ReconciledStatement
  contextLabel: string
}>()

const expanded = ref(true)

function cellText(amount: StatementAmount): string {
  return amount.display
}

function flag(amount: StatementAmount): string {
  if (amount.status === 'partial') return '(partial)'
  if (amount.status === 'unavailable') return '(unavailable)'
  return ''
}

function returnFlag(entry: StatementReturn): string {
  if (entry.status === 'partial') return '(partial)'
  if (entry.status === 'not_available' || entry.status === 'not_relevant') {
    return ''
  }
  return ''
}

const REASON_TEXT: Record<string, string> = {
  missing_price: 'missing prices',
  missing_fx: 'missing FX rates',
  option_unrealized_not_attributed: 'open options are not attributed',
  in_kind_flows_unclassified: 'external in-kind transfers are unclassified',
  crypto_coin_fee_not_attributed: 'a coin-denominated fee is not attributed',
  unexplained_difference: 'components do not fully explain the net result',
  no_accounts_selected: 'no accounts selected',
}

function reasonText(reasons: readonly string[]): string {
  return reasons
    .filter((reason) => reason !== 'unexplained_difference')
    .map((reason) => REASON_TEXT[reason] ?? reason)
    .join('; ')
}

const statusNotice = computed(() => {
  const { statement } = props
  if (statement.status === 'unavailable') {
    return `The statement is unavailable: ${reasonText(statement.reasons) || 'reason unavailable'}.`
  }
  if (statement.netResult.reconciliation === 'unreconciled') {
    return (
      `Unreconciled difference ${statement.netResult.unexplainedDifference.display}: ` +
      'the components above do not fully explain the net result.'
    )
  }
  if (statement.status === 'partial') {
    const detail = reasonText(statement.reasons)
    return detail ? `Partial statement: ${detail}.` : 'Partial statement.'
  }
  return null
})

interface BreakdownRow {
  key: string
  label: string
  display: string
  flag: string
  flagTitle?: string
}

const breakdownRows = computed<readonly BreakdownRow[]>(() => {
  const components = props.statement.netResult.components
  const rows: BreakdownRow[] = [
    {
      key: 'realizedPrice',
      label: 'Realized gains / losses',
      display: components.realizedPrice.display,
      flag: flag(components.realizedPrice),
      flagTitle: components.realizedPrice.reason,
    },
    {
      key: 'unrealizedPrice',
      label: 'Unrealized gains / losses',
      display: components.unrealizedPrice.display,
      flag: flag(components.unrealizedPrice),
      flagTitle: components.unrealizedPrice.reason,
    },
    {
      key: 'income',
      label: 'Dividends & interest',
      display: components.income.display,
      flag: flag(components.income),
      flagTitle: components.income.reason,
    },
    {
      key: 'fees',
      label: 'Fees',
      display: components.fees.display,
      flag: flag(components.fees),
      flagTitle: components.fees.reason,
    },
    {
      key: 'taxes',
      label: 'Taxes',
      display: components.taxes.display,
      flag: flag(components.taxes),
      flagTitle: components.taxes.reason,
    },
    {
      key: 'fx',
      label: 'FX effect',
      display: components.fx.display,
      flag: flag(components.fx),
      flagTitle: components.fx.reason,
    },
  ]
  // Other flows render only when they carry value or a problem to show.
  if (components.otherFlows.raw !== '0' && components.otherFlows.raw !== null) {
    rows.push({
      key: 'otherFlows',
      label: 'Other flows',
      display: components.otherFlows.display,
      flag: flag(components.otherFlows),
      flagTitle: components.otherFlows.reason,
    })
  }
  return rows
})

const displayRoundingNote = computed(() => {
  const { statement } = props
  const digits = statement.context.digits
  const adjustment = displayRoundingAdjustment(
    breakdownRows.value,
    statement.netResult.controlTotal,
    digits,
  )
  if (adjustment === null || adjustment === BigInt(0)) return null
  const subtotal = parseDisplayScaled(statement.netResult.controlTotal.display, digits)
  if (subtotal === null) return null
  const rowsSum = subtotal - adjustment
  const magnitude = adjustment < 0n ? -adjustment : adjustment
  const sign = adjustment < 0n ? '-' : '+'
  return (
    `The displayed components sum to ${formatScaledInteger(rowsSum, digits)}; ` +
    `the net result differs by ${sign}${formatScaledInteger(magnitude, digits)} ` +
    'because each row is rounded for display.'
  )
})
</script>

<style scoped>
.statement-section {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.statement-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 12px 48px;
  align-items: start;
}

.statement-rows {
  display: grid;
  gap: 8px;
  margin: 0;
}

.statement-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: baseline;
  min-width: 0;
}

.statement-row dt {
  font-size: 0.875rem;
  color: rgb(var(--v-theme-text-secondary));
}

.statement-row dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  text-align: right;
  overflow-wrap: anywhere;
}

.statement-row.subtotal {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: 8px;
}

.statement-row.subtotal dt {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}

.net-result-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.statement-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: rgb(var(--v-theme-primary));
  background: transparent;
  cursor: pointer;
}

.statement-toggle:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.breakdown {
  padding: 8px 0 0 20px;
  min-width: 0;
}

.breakdown-row dt {
  font-size: 0.8125rem;
}

.breakdown-row dd {
  font-size: 0.9375rem;
}

.breakdown-help {
  margin-top: 6px;
}

.amount-flag {
  font-size: 0.75rem;
  color: rgb(var(--v-theme-warning));
}

.statement-status {
  margin: 8px 0;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
}

.statement-row.total-row {
  border-top: 2px solid rgba(var(--v-border-color), var(--v-border-opacity));
  margin-top: 8px;
  padding-top: 10px;
}

.statement-row.total-row dt {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 700;
  font-size: 1rem;
}

.statement-row.total-row dd {
  font-weight: 700;
  font-size: 1.25rem;
}

.returns-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.returns-label {
  margin: 0 0 4px;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-text-secondary));
}

.returns-value {
  margin: 0;
  font-size: 2rem;
  line-height: 1.2;
  font-weight: 650;
  color: rgb(var(--v-theme-primary));
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 959px) {
  .statement-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
