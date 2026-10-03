// C3 Task 3: renderer policy and the owned ECharts lifecycle. The lazy
// renderer stays behind eligibility; interaction survives same-context
// refresh and resize; disposal is exactly-once; a late import/error after
// disposal can never resurrect or cross-mutate instances. The chart wrapper
// is stubbed to capture the exact options our renderer feeds it — assertions
// target real option state by series id.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import type { ChartInteraction } from '../interaction'
import type { ChartDocument, NavResult } from '../contracts'
import { navWireFixture } from './navFixtures'
import { parseNavEnvelope } from '../parseChartEnvelope'
import { defaultInteraction } from '../interaction'

import { resolveRenderer } from '../rendererPolicy'

// Shared hoisted state so the hoisted vue-echarts mock can record mounts.
const chartState = vi.hoisted(() => ({
  mounts: 0,
  unmounts: 0,
  captured: [] as Array<{ option: Record<string, unknown>; updateOptions: Record<string, unknown> | undefined }>,
}))

vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup(props: { option: Record<string, unknown>; updateOptions?: Record<string, unknown> }) {
        chartState.mounts += 1
        chartState.captured.push({
          get option() { return props.option },
          get updateOptions() { return props.updateOptions },
        })
        return () => h('div', { class: 'echarts-stub' })
      },
      unmounted() {
        chartState.unmounts += 1
      },
    },
  }
})

import ChartHost from '../ChartHost.vue'
import EChartsNav from '../EChartsNav.vue'

function parsedDocument(): ChartDocument {
  const parsed = parseNavEnvelope(navWireFixture('asset_type', 'M'))
  if (parsed.capability !== 'v2') throw new Error('fixture must parse as v2')
  return parsed.document
}

function v2Result(): NavResult {
  return { capability: 'v2', legacy: { labels: ['Jan-26'], currency: 'USDk', datasets: [] }, document: parsedDocument() }
}

function legacyOnlyResult(): NavResult {
  return { capability: 'legacy_only', legacy: { labels: ['Jan-26'], currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1] }] } }
}

function mountHost(props: {
  result: NavResult
  loading?: boolean
  requested?: 'chartjs' | 'echarts'
  interaction?: ChartInteraction
}) {
  const document = parsedDocument()
  return mount(ChartHost, {
    props: {
      loading: false,
      requested: 'echarts',
      ...props,
      interaction: props.interaction ?? defaultInteraction(document),
    },
    slots: { default: () => h('div', { class: 'incumbent-renderer' }) },
  })
}

function emittedInteraction(wrapper: { emitted: (event: string) => unknown[][] | undefined }, index = 0): ChartInteraction {
  const events = wrapper.emitted('update:interaction') as ChartInteraction[][] | undefined
  if (!events || !events[index]) throw new Error('missing update:interaction event')
  return events[index][0]
}

beforeEach(() => {
  chartState.mounts = 0
  chartState.unmounts = 0
  chartState.captured.length = 0
})

describe('resolveRenderer policy', () => {
  it('keeps Chart.js unless ECharts is requested', () => {
    expect(resolveRenderer('chartjs', v2Result())).toBe('chartjs')
  })

  it('allows ECharts only for validated v2 results', () => {
    expect(resolveRenderer('echarts', v2Result())).toBe('echarts')
    expect(resolveRenderer('echarts', legacyOnlyResult())).toBe('chartjs')
    expect(resolveRenderer('echarts', null)).toBe('chartjs')
  })
})

describe('ChartHost lazy lifecycle', () => {
  it('mounts the ECharts pilot for an eligible v2 result and feeds controlled options', async () => {
    const wrapper = mountHost({ result: v2Result() })
    await flushPromises()
    expect(wrapper.find('.echarts-stub').exists()).toBe(true)
    expect(wrapper.find('.incumbent-renderer').exists()).toBe(false)
    const option = chartState.captured.at(-1)!.option as { series?: Array<{ id: string }> }
    expect(option.series!.map((series) => series.id)).toContain('metric:irr_interval')
    wrapper.unmount()
  })

  it('keeps the incumbent renderer for legacy_only results and chartjs requests', async () => {
    const legacy = mountHost({ result: legacyOnlyResult() })
    await flushPromises()
    expect(legacy.find('.incumbent-renderer').exists()).toBe(true)
    expect(chartState.mounts).toBe(0)
    legacy.unmount()
    const off = mountHost({ result: v2Result(), requested: 'chartjs' })
    await flushPromises()
    expect(off.find('.incumbent-renderer').exists()).toBe(true)
    expect(chartState.mounts).toBe(0)
    off.unmount()
  })

  it('preserves interaction across a same-context refresh with an aria-busy overlay while loading', async () => {
    const document = parsedDocument()
    const hidden: ChartInteraction = {
      ...defaultInteraction(document),
      visibleSeriesIds: defaultInteraction(document).visibleSeriesIds.filter((id) => id !== 'asset_type:Cash'),
      inspectedPeriodKey: document.periods[1].key,
    }
    const wrapper = mountHost({ result: v2Result(), interaction: hidden })
    await flushPromises()
    await wrapper.setProps({ loading: true })
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(wrapper.find('.echarts-stub').exists()).toBe(true)
    await wrapper.setProps({ result: v2Result(), loading: false })
    await flushPromises()
    const option = chartState.captured.at(-1)!.option as { series?: Array<{ id: string }> }
    expect(option.series!.map((series) => series.id)).not.toContain('asset_type:Cash')
    expect(option.series!.map((series) => series.id)).toContain('metric:irr_interval')
    wrapper.unmount()
  })

  it('replaces option series wholesale so hidden or stale series never merge back', async () => {
    const document = parsedDocument()
    const all = defaultInteraction(document)
    const wrapper = mountHost({ result: v2Result(), interaction: all })
    await flushPromises()
    expect(chartState.captured.at(-1)!.updateOptions).toMatchObject({ notMerge: true })
    await wrapper.setProps({ interaction: { ...all, visibleSeriesIds: all.visibleSeriesIds.slice(0, 2) } })
    await flushPromises()
    const option = chartState.captured.at(-1)!.option as { series?: Array<{ id: string }> }
    expect(option.series!.length).toBe(2)
    wrapper.unmount()
  })

  it('disposes exactly once per mount across repeated mount/unmount cycles', async () => {
    for (let cycle = 0; cycle < 2; cycle += 1) {
      const wrapper = mountHost({ result: v2Result() })
      await flushPromises()
      wrapper.unmount()
      await flushPromises()
    }
    expect(chartState.mounts).toBe(2)
    expect(chartState.unmounts).toBe(2)
  })

  it('offers recovery from a render failure without converting into an empty chart', async () => {
    const wrapper = mountHost({ result: v2Result() })
    await flushPromises()
    wrapper.findComponent({ name: 'EChartsNav' }).vm.$emit('render-error', new Error('canvas exploded'))
    await flushPromises()
    expect(wrapper.find('[data-testid="chart-render-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('canvas exploded')
    expect(wrapper.find('.echarts-stub').exists()).toBe(false)
    await wrapper.find('[data-testid="chart-render-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.echarts-stub').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chart-render-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('fallback is an explicit user choice backed by the same accepted result', async () => {
    const wrapper = mountHost({ result: v2Result() })
    await flushPromises()
    wrapper.findComponent({ name: 'EChartsNav' }).vm.$emit('render-error', new Error('boom'))
    await flushPromises()
    await wrapper.find('[data-testid="chart-render-fallback"]').trigger('click')
    expect(wrapper.emitted('fallback')).toBeTruthy()
    expect(wrapper.emitted('fallback')!.length).toBe(1)
    wrapper.unmount()
  })
})

describe('EChartsNav renderer events', () => {
  it('maps pointer clicks and dataZoom into server period keys without touching values', async () => {
    const document = parsedDocument()
    const wrapper = mount(EChartsNav, {
      props: { document, interaction: defaultInteraction(document) },
    })
    await flushPromises()
    const chart = wrapper.findComponent({ name: 'VChart' })
    chart.vm.$emit('click', { dataIndex: 1 })
    let update = emittedInteraction(wrapper)
    expect(update.inspectedPeriodKey).toBe(document.periods[1].key)
    expect(update.viewport).toBeNull()
    // The controlled model requires the parent to feed state back before the
    // next event can build on it — exactly how the panel wires the loop.
    await wrapper.setProps({ interaction: update })
    chart.vm.$emit('datazoom', { start: 0, end: 40 })
    update = emittedInteraction(wrapper, 1)
    expect(update.viewport!.firstPeriodKey).toBe(document.periods[0].key)
    expect(update.inspectedPeriodKey).toBe(document.periods[1].key)
    wrapper.unmount()
  })

  it('cleans up its resize observers/listeners on unmount', async () => {
    const hasObserver = typeof ResizeObserver !== 'undefined'
    const disconnectSpy = hasObserver ? vi.spyOn(ResizeObserver.prototype, 'disconnect') : null
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const document = parsedDocument()
    const wrapper = mount(EChartsNav, { props: { document, interaction: defaultInteraction(document) } })
    await flushPromises()
    wrapper.unmount()
    expect(hasObserver ? disconnectSpy : removeSpy).toHaveBeenCalled()
    if (disconnectSpy) disconnectSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('never mutates the validated document while rendering', async () => {
    const document = parsedDocument()
    const before = structuredClone(document)
    const wrapper = mount(EChartsNav, { props: { document, interaction: defaultInteraction(document) } })
    await flushPromises()
    wrapper.unmount()
    expect(document).toEqual(before)
  })
})
