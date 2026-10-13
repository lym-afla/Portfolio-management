// Review-round regressions for the MEASURED fit loop in WorkspaceActions:
// convergence when the width estimate leaves real overflow, the degenerate
// wrap fallback, unmount-safety of the asynchronous measurement, refits for
// resizes arriving mid-fit, and keyboard-focus preservation across tier
// changes. Layout reads (clientWidth/scrollWidth/rAF) are stubbed so each
// scenario is deterministic.
import { beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'
import { fitVisibleActions } from '@/components/workspace/fitActions'

vi.mock('@/components/workspace/fitActions.ts', () => ({
  fitVisibleActions: vi.fn(),
}))
const fitMock = vi.mocked(fitVisibleActions)

const primary = { id: 'add-transaction', label: 'Add transaction', icon: 'mdi-plus' }
const candidates = [
  { id: 'c1', label: 'Candidate one', icon: 'mdi-dot' },
  { id: 'c2', label: 'Candidate two', icon: 'mdi-dot' },
  { id: 'c3', label: 'Candidate three', icon: 'mdi-dot' },
  { id: 'c4', label: 'Candidate four', icon: 'mdi-dot' },
]

const vuetify = createVuetify({ components, directives })

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

// --- Deterministic layout stubs -------------------------------------------
// The fit queue is microtask-based (rAF-free by design), so flushing
// promises drives the whole chain deterministically.
class ResizeObserverStub {
  static instances: ResizeObserverStub[] = []
  callback: () => void
  constructor(callback: () => void) {
    this.callback = callback
    ResizeObserverStub.instances.push(this)
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

async function settle() {
  for (let round = 0; round < 12; round += 1) {
    await flushPromises()
  }
  await flushPromises()
}

beforeEach(() => {
  fitMock.mockReset()
  ResizeObserverStub.instances = []
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function mountActions(props?: Record<string, unknown>) {
  const wrapper = mount(WorkspaceActions, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: {
      primary,
      secondary: candidates.slice(0, 2),
      overflow: candidates.slice(2),
      ...props,
    },
  })
  // The measured strip is the component root (wrapper.element is the mount
  // container when attachTo is used).
  const strip = wrapper.get('.workspace-actions-strip').element as HTMLElement
  Object.defineProperty(strip, 'clientWidth', { configurable: true, value: 900 })
  const row = wrapper.get('.workspace-actions-row').element as HTMLElement
  Object.defineProperty(row, 'clientWidth', { configurable: true, value: 900 })
  return wrapper
}

function stubRowOverflow(wrapper, overflowsWhile: (count: number) => boolean) {
  const row = wrapper.get('.workspace-actions-row').element
  Object.defineProperty(row, 'scrollWidth', {
    configurable: true,
    get: () => (overflowsWhile(wrapper.vm.visibleCount) ? 1400 : 400),
  })
}

function fireResize(width = 900, index = -1) {
  const observer = ResizeObserverStub.instances.at(index)
  expect(observer).toBeTruthy()
  observer!.callback([{ contentRect: { width } }])
}

describe('WorkspaceActions measured fit corrections', () => {
  it('sheds actions one at a time until the row really fits when the estimate leaves overflow', async () => {
    const wrapper = await mountActions()
    stubRowOverflow(wrapper, (count) => count > 2)
    // A stale estimate claims everything fits, but the real row overflows
    // while more than two actions are direct: the correction must reduce the
    // RETAINED count (2), not recompute the same estimate forever.
    fitMock.mockReturnValue(4)
    fireResize()
    await settle()
    expect(wrapper.vm.visibleCount).toBe(2)
    expect(wrapper.get('.workspace-actions-row').classes()).not.toContain(
      'workspace-actions-row--wrapped'
    )
    wrapper.unmount()
  })

  it('wraps instead of clipping when even the primary action and the activator cannot fit', async () => {
    const wrapper = await mountActions()
    stubRowOverflow(wrapper, () => true)
    fitMock.mockReturnValue(0)
    fireResize()
    await settle()
    expect(wrapper.vm.visibleCount).toBe(0)
    expect(wrapper.get('.workspace-actions-row').classes()).toContain(
      'workspace-actions-row--wrapped'
    )
    wrapper.unmount()
  })

  it('unmount during measurement leaves no stale continuation and touches no replacement', async () => {
    const rejections: unknown[] = []
    const onRejection = (reason: unknown) => rejections.push(reason)
    process.on('unhandledRejection', onRejection)
    fitMock.mockReturnValue(2)
    const first = await mountActions()
    stubRowOverflow(first, () => false)
    fireResize()
    // Let the fit reach its first await, then unmount mid-measurement.
    await flushPromises()
    first.unmount()
    // A replacement instance mounts with its own state.
    const second = await mountActions()
    await settle()
    fireResize(0)
    await settle()
    await new Promise((resolve) => setTimeout(resolve, 20))
    process.off('unhandledRejection', onRejection)
    expect(rejections).toHaveLength(0)
    // The replacement behaves normally and was not touched by the stale run.
    expect(second.vm.visibleCount).toBe(2)
    second.unmount()
  })

  it('a resize observed while a fit is running triggers a refit instead of being swallowed', async () => {
    const wrapper = await mountActions()
    stubRowOverflow(wrapper, () => false)
    fitMock.mockReturnValue(3)
    fireResize(900)
    // Start the fit (it is now inside its measurement awaits), THEN fire the
    // trailing resize at a NEW width: it must queue a refit, not be
    // swallowed. Same-width events are the fit's own aftereffect and are
    // filtered. (The mount fit is the first call, so three runs are expected.)
    await flushPromises()
    fireResize(760)
    await settle()
    expect(fitMock).toHaveBeenCalledTimes(3)
    expect(wrapper.vm.visibleCount).toBe(3)
    wrapper.unmount()
  })

  it('focus follows the action into the activator when its row slot disappears', async () => {
    const wrapper = await mountActions()
    stubRowOverflow(wrapper, (count) => count > 4)
    fitMock.mockReturnValue(4)
    fireResize()
    await settle()
    expect(wrapper.vm.visibleCount).toBe(4)
    const third = wrapper.findAll('[data-action]')[2]
    ;(third.element as HTMLElement).focus()
    expect(document.activeElement).toBe(third.element)
    // The estimate changes: only one action stays direct, so the focused
    // action moves into the menu — focus must land on the activator.
    fitMock.mockReturnValue(1)
    stubRowOverflow(wrapper, (count) => count > 1)
    fireResize(760)
    await settle()
    expect(wrapper.vm.visibleCount).toBe(1)
    expect(document.activeElement?.getAttribute('data-testid')).toBe(
      'workspace-actions-more'
    )
    wrapper.unmount()
  })

  it('keeps focus on an action that survives the refit without stealing it', async () => {
    const wrapper = await mountActions()
    stubRowOverflow(wrapper, () => false)
    fitMock.mockReturnValue(4)
    fireResize()
    await settle()
    const second = wrapper.findAll('[data-action]')[1]
    ;(second.element as HTMLElement).focus()
    fitMock.mockReturnValue(3)
    fireResize(760)
    await settle()
    expect(wrapper.vm.visibleCount).toBe(3)
    expect(document.activeElement).toBe(second.element)
    wrapper.unmount()
  })
})
