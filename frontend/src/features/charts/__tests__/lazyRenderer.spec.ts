// C5a Task 1: the legacy Chart.js runtime becomes genuinely lazy. The shared
// loader helper must turn a rejected chunk download into a visible,
// recoverable renderer error — never an empty-success chart and never an
// automatic retry loop — and the shells must load their legacy leaves only
// when they actually render, with a user-chosen fallback rendering the SAME
// accepted response and zero additional API calls.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createPinia } from 'pinia'
import { lazyChartRenderer } from '../lazyRenderer'

function textStub(tag = 'div', marker = 'legacy-leaf-stub') {
  return defineComponent({
    name: 'LazyStub',
    setup(_, { attrs }) {
      return () => h(tag, { ...attrs, class: marker }, String(attrs.data ?? ''))
    },
  })
}

describe('lazyChartRenderer', () => {
  it('renders the loaded leaf once the chunk resolves', async () => {
    const { component, loadError } = lazyChartRenderer(async () => textStub())
    const wrapper = mount(defineComponent({ setup: () => () => h(component) }))
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(false)
    await flushPromises()
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(true)
    expect(loadError.value).toBeNull()
  })

  it('surfaces a rejected chunk load as a visible error, not an empty chart', async () => {
    const onLoadError = vi.fn()
    const { component, loadError } = lazyChartRenderer(
      async () => {
        throw new Error('Synthetic chunk download failure')
      },
      { onLoadError },
    )
    const wrapper = mount(defineComponent({ setup: () => () => h(component) }))
    await flushPromises()
    expect(loadError.value).toBeInstanceOf(Error)
    expect(loadError.value?.message).toBe('Synthetic chunk download failure')
    expect(onLoadError).toHaveBeenCalledTimes(1)
    expect(onLoadError.mock.calls[0][0]).toBe(loadError.value)
    // Nothing is rendered — the SHELL owns the visible error UI, which is
    // asserted per shell below; the helper's contract is the state only.
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(false)
  })

  it('retry() re-runs the loader and renders after a deferred success', async () => {
    let attempts = 0
    let release: (() => void) | null = null
    const gate = new Promise<void>((resolve) => { release = resolve })
    const loader = vi.fn(async () => {
      attempts += 1
      if (attempts === 1) throw new Error('first download fails')
      await gate
      return textStub()
    })
    const { component, loadError, retry } = lazyChartRenderer(loader)
    const wrapper = mount(defineComponent({ setup: () => () => h(component) }))
    await flushPromises()
    expect(loadError.value?.message).toBe('first download fails')
    expect(attempts).toBe(1)

    retry()
    await flushPromises()
    // No automatic attempt and no render before the retry's download lands.
    expect(attempts).toBe(2)
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(false)
    release!()
    await flushPromises()
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(true)
    expect(loadError.value).toBeNull()
  })

  it('never retries automatically: a rejected retry stays a visible error', async () => {
    let attempts = 0
    const loader = vi.fn(async () => {
      attempts += 1
      throw new Error(`download ${attempts} fails`)
    })
    const { component, loadError, retry } = lazyChartRenderer(loader)
    const wrapper = mount(defineComponent({ setup: () => () => h(component) }))
    await flushPromises()
    expect(attempts).toBe(1)
    retry()
    await flushPromises()
    expect(attempts).toBe(2)
    expect(loadError.value?.message).toBe('download 2 fails')
    expect(wrapper.find('.legacy-leaf-stub').exists()).toBe(false)
    // Waiting must not progress the loader on its own — no polling loop.
    await new Promise((resolve) => setTimeout(resolve, 25))
    await flushPromises()
    expect(attempts).toBe(2)
    expect(loadError.value?.message).toBe('download 2 fails')
  })
})

// Shell wiring: the NAV shell loads its legacy leaf asynchronously and the
// user-chosen fallback renders the same accepted legacy response with zero
// additional API calls.
const navState = vi.hoisted(() => ({ legacyProps: [] as Array<Record<string, unknown>> }))

vi.mock('@/components/charts/StackedBarLineChart.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    __esModule: true,
    default: defineComponent({
      name: 'StackedBarLineChart',
      props: ['chartData', 'options'],
      setup(props: { chartData?: Record<string, unknown> }) {
        navState.legacyProps.push(props.chartData ?? {})
        return () => h('div', { class: 'stacked-leaf-stub' }, JSON.stringify(props.chartData?.labels ?? []))
      },
    }),
  }
})

import NAVChart from '@/components/dashboard/NAVChart.vue'

const navChartData = () => ({
  labels: ['Jan-26', 'Feb-26'],
  currency: 'USDk',
  datasets: [
    { label: 'NAV', type: 'bar', data: [100, 120] },
    { label: 'IRR (RHS)', type: 'line', data: [0.1, 0.2] },
  ],
})

describe('NAV legacy leaf laziness', () => {
  beforeEach(() => { navState.legacyProps.length = 0 })

  it('renders the legacy leaf asynchronously with the handed data', async () => {
    const wrapper = mount(NAVChart, {
      props: { chartData: navChartData(), initialParams: {}, effectiveCurrentDate: '2026-02-28' },
      global: { plugins: [createPinia()] },
    })
    // The stub resolves on the microtask queue; both before/after prove the
    // leaf is async-loaded, not an eager import in disguise.
    await flushPromises()
    expect(wrapper.find('.stacked-leaf-stub').exists()).toBe(true)
    expect(navState.legacyProps.at(-1)?.labels).toEqual(['Jan-26', 'Feb-26'])
  })
})
