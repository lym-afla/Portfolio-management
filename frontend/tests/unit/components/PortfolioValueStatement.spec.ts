import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PortfolioValueStatement from '@/components/dashboard/PortfolioValueStatement.vue'
import type { ReconciledStatement } from '@/services/api/dashboard'
import { amount, statementFixture } from './statement-fixture'

const vuetify = createVuetify({ components, directives })

function mountStatement(statement: ReconciledStatement) {
  return mount(PortfolioValueStatement, {
    props: { statement, contextLabel: 'Brokerage A · 2026-10-15 · USD' },
    global: { plugins: [vuetify] },
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe('PortfolioValueStatement', () => {
  it('renders zero rows as the backend dash and keeps amounts right-aligned', () => {
    const wrapper = mountStatement(statementFixture())
    const dds = wrapper.findAll('dd')
    expect(dds.length).toBeGreaterThan(0)
    for (const dd of dds) {
      expect(dd.classes()).toContain('workspace-number')
    }
    const zero = wrapper.findAll('.breakdown-row').at(-1)
    expect(zero?.text()).not.toContain('Other flows')
    wrapper.unmount()
  })

  it('shows the other-flows row only when it carries value or a problem', () => {
    const statement = statementFixture()
    statement.netResult.components.otherFlows = amount('$12.00', { raw: '12' })
    const wrapper = mountStatement(statement)
    const labels = wrapper.findAll('.breakdown-row dt').map((node) => node.text())
    expect(labels).toContain('Other flows')
    wrapper.unmount()
  })

  it('marks partial rows with their reason and unavailable returns honestly', () => {
    const statement = statementFixture()
    statement.netResult.components.income = amount('$3,500.00', {
      raw: '3500',
      status: 'partial',
      reason: 'missing_fx',
    })
    statement.returns.irr = {
      value: null,
      display: 'N/A',
      status: 'not_available',
      reason: 'solver_unavailable',
    }
    statement.status = 'partial'
    statement.reasons = ['missing_fx']
    const wrapper = mountStatement(statement)
    const flag = wrapper.find('.amount-flag[title="missing_fx"]')
    expect(flag.exists()).toBe(true)
    expect(flag.text()).toContain('(partial)')
    expect(wrapper.find('[data-testid="statement-status"]').text()).toContain(
      'missing FX rates',
    )
    expect(wrapper.find('[data-testid="irr-since-inception"]').text()).toContain('N/A')
    wrapper.unmount()
  })

  it('exposes a labelled display-rounding adjustment when rounded rows disagree', () => {
    const statement = statementFixture()
    // Rows rounded independently: 8,000.00 + 7,000.00 + 3,500.00 - 1,000.00
    // - 500.00 + 500.01 sums to 17,500.01 against a 17,500.00 subtotal.
    statement.netResult.components.fx = amount('$500.01', { raw: '500.01' })
    const wrapper = mountStatement(statement)
    const note = wrapper.find('[data-testid="display-rounding-note"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('0.01')
    expect(note.text()).toContain('rounded for display')
    wrapper.unmount()
  })

  it('emits no rounding note when the displayed rows add up', () => {
    const wrapper = mountStatement(statementFixture())
    expect(wrapper.find('[data-testid="display-rounding-note"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('toggles via a native button (keyboard operable) with visible focus styling', async () => {
    const wrapper = mountStatement(statementFixture())
    const toggle = wrapper.find('[data-testid="breakdown-toggle"]')
    // A native button: Enter/Space activation is browser-native, and the
    // focus-visible outline is defined in the component styles.
    expect(toggle.element.tagName).toBe('BUTTON')
    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="net-result-breakdown"]').element.style.display).toBe('none')
    await wrapper.find('[data-testid="breakdown-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="net-result-breakdown"]').element.style.display).toBe('')
    wrapper.unmount()
  })
})

describe('display rounding vs reconciliation separation', () => {
  it('shows no rounding note when a component is missing', () => {
    const statement = statementFixture()
    statement.status = 'partial'
    statement.reasons = ['missing_fx']
    statement.netResult.reconciliation = 'incomplete'
    statement.netResult.components.income = {
      raw: null,
      display: 'N/A',
      status: 'unavailable',
      reason: 'missing_fx',
    }
    const wrapper = mountStatement(statement)
    expect(wrapper.find('[data-testid="display-rounding-note"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the actual unexplained difference for incomplete statements too', () => {
    const statement = statementFixture()
    statement.status = 'partial'
    statement.reasons = ['missing_fx']
    statement.netResult.reconciliation = 'incomplete'
    statement.netResult.unexplainedDifference = {
      raw: '500',
      display: '$500.00',
      status: 'ok',
    }
    const wrapper = mountStatement(statement)
    const status = wrapper.find('[data-testid="statement-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('Unreconciled difference')
    expect(status.text()).toContain('$500.00')
    wrapper.unmount()
  })

  it('keeps a small incomplete difference out of the rounding claim but visible as partial', () => {
    const statement = statementFixture()
    statement.status = 'partial'
    statement.reasons = ['missing_fx']
    statement.netResult.reconciliation = 'incomplete'
    statement.netResult.unexplainedDifference = { raw: '0.01', display: '$0.01', status: 'ok' }
    const wrapper = mountStatement(statement)
    expect(wrapper.find('[data-testid="display-rounding-note"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="statement-status"]').text()).toContain('Partial statement')
    wrapper.unmount()
  })
})

describe('statementDisplay', () => {
  it('parses backend display strings into scaled integers without floats', async () => {
    const { parseDisplayScaled, formatScaledInteger, displayRoundingAdjustment } =
      await import('@/components/dashboard/statementDisplay')
    expect(parseDisplayScaled('$1,234.56', 2)).toBe(123456n)
    expect(parseDisplayScaled('($5.00)', 2)).toBe(-500n)
    expect(parseDisplayScaled('–', 2)).toBe(0n)
    expect(parseDisplayScaled('N/A', 2)).toBe(null)
    expect(parseDisplayScaled('NA', 2)).toBe(null)
    expect(parseDisplayScaled('N/R', 2)).toBe(null)
    expect(parseDisplayScaled('$0.00', 2)).toBe(0n)
    expect(parseDisplayScaled('junk', 2)).toBe(null)
    expect(formatScaledInteger(123456n, 2)).toBe('1,234.56')
    expect(formatScaledInteger(-5n, 2)).toBe('-0.05')
    const adjustment = displayRoundingAdjustment(
      [{ display: '$8,000.00' }, { display: '($0.01)' }],
      { display: '$7,999.98' },
      2,
    )
    expect(adjustment).toBe(-1n)
  })
})
