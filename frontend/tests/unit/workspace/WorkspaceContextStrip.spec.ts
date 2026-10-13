import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import WorkspaceContextStrip from '@/components/workspace/WorkspaceContextStrip.vue'
import { toContextPatch } from '@/components/workspace/contextIntent'
import { useWorkspaceContextView } from '@/components/workspace/useWorkspaceContextView'
import { reactive, ref } from 'vue'
import type { WorkspaceContextView } from '@/components/workspace/types'

const committed = {
  revision: 4,
  accountSelection: { type: 'account' as const, id: 1 },
  effectiveCurrentDate: '2026-09-08',
  currency: 'USD',
  digits: 2,
}
const view: WorkspaceContextView = {
  committed,
  accountLabel: 'Brokerage A',
  pendingLabel: 'Brokerage B',
  isReady: true,
  isTransitioning: true,
  errorMessage: null,
}
// The header controls (account select, valuation date, currency) ARE the
// committed-context display. The strip must not repeat that text — the
// duplicated summary line was removed in the presentation corrections —
// while the preferences action and pending/error feedback stay.
it('keeps feedback and preferences without duplicating the committed context text', () => {
  const wrapper = mount(WorkspaceContextStrip, {
    props: { view },
    slots: { controls: '<button>Existing controls</button>' },
  })
  const text = wrapper.text()
  expect(text).not.toContain('Valuation date:')
  expect(text).not.toContain('Reporting currency:')
  expect(wrapper.find('[data-testid="committed-account"]').exists()).toBe(false)
  expect(wrapper.findAll('[role="status"]')).toHaveLength(1)
  expect(wrapper.get('[role="status"]').text()).toContain('Brokerage B')
  expect(
    wrapper
      .findAll('button')
      .map((b) => b.text())
      .join('|')
  ).toContain('Existing controls')
  expect(wrapper.get('[aria-label="Display preferences"]').text()).toBe(
    'Display preferences'
  )
})
it('announces failure without replacing confirmed data and emits preferences intent', async () => {
  const wrapper = mount(WorkspaceContextStrip, {
    props: {
      view: { ...view, isTransitioning: false, errorMessage: 'Account denied' },
    },
  })
  expect(wrapper.get('[role="alert"]').text()).toBe('Account denied')
  expect(wrapper.find('[role="status"]').exists()).toBe(false)
  await wrapper.get('[aria-label="Display preferences"]').trigger('click')
  expect(wrapper.emitted('open-preferences')).toHaveLength(1)
})
it('disables preferences until the context is ready', () => {
  const wrapper = mount(WorkspaceContextStrip, {
    props: {
      view: {
        ...view,
        isReady: false,
        isTransitioning: false,
        committed: { ...committed, currency: null, effectiveCurrentDate: null },
      },
    },
  })
  expect(
    wrapper.get('[aria-label="Display preferences"]').attributes('disabled')
  ).toBeDefined()
})
it('builds complete settings tuples, retaining precision zero and isolated account intents', () => {
  expect(toContextPatch({ currency: 'EUR' }, committed, true)).toEqual({
    effectiveCurrentDate: '2026-09-08',
    currency: 'EUR',
    digits: 2,
  })
  expect(toContextPatch({ digits: 0 }, committed, true)).toEqual({
    effectiveCurrentDate: '2026-09-08',
    currency: 'USD',
    digits: 0,
  })
  expect(
    toContextPatch(
      { accountSelection: { type: 'group', id: 8 } },
      committed,
      true
    )
  ).toEqual({ accountSelection: { type: 'group', id: 8 } })
  expect(() => toContextPatch({ currency: 'EUR' }, committed, false)).toThrow(
    'not ready'
  )
})
it('derives labels reactively from already loaded choices and retains committed state on failure', () => {
  const state = reactive({
    committed,
    isReady: true,
    isTransitioning: false,
    transitionError: null as Error | null,
  })
  const label = ref('Brokerage A')
  const pending = ref<string | null>(null)
  const display = useWorkspaceContextView(
    state,
    () => label.value,
    () => pending.value
  )
  pending.value = 'Brokerage B'
  state.isTransitioning = true
  expect(display.value).toMatchObject({
    accountLabel: 'Brokerage A',
    pendingLabel: 'Brokerage B',
    committed,
  })
  state.isTransitioning = false
  state.transitionError = new Error('Denied')
  expect(display.value).toMatchObject({
    accountLabel: 'Brokerage A',
    pendingLabel: null,
    errorMessage: 'Denied',
  })
})
