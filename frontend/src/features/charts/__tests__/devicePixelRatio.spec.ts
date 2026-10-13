// Phase C Task 6: sharp charts at native zoom. zrender's canvas painter fixes
// devicePixelRatio at init and its resize() never re-reads it, so a DPR
// change (native 200% zoom, monitor switch) leaves the stale low-resolution
// backing store CSS-scaled — blurry. The fix re-initializes the chart (VChart
// remount) when the DPR changes; interaction state is parent-owned and
// survives. RED-first against the pre-fix sources.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, ref } from 'vue'

const chartState = vi.hoisted(() => ({ mounts: 0 }))

vi.mock('vue-echarts', async () => {
  const { h: hh } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup() {
        chartState.mounts += 1
        return () => hh('div', { class: 'echarts-stub' })
      },
    },
  }
})

import EChartsNav from '../EChartsNav.vue'
import { watchDevicePixelRatio } from '../devicePixelRatio'
import { navWireFixture } from './navFixtures'
import { parseNavEnvelope } from '../parseChartEnvelope'
import { defaultInteraction } from '../interaction'
import type { ChartDocument } from '../contracts'

/** Minimal fake of the matchMedia surface the watcher uses: one resolution
    query alive at a time, test-controlled change firing. */
class FakeQuery {
  constructor(public value: string) {}
  listener: ((this: MediaQueryList, event: MediaQueryListEvent) => void) | null = null
  addEventListener(type: string, listener: () => void): void {
    expect(type).toBe('change')
    this.listener = listener as never
  }
  removeEventListener(): void {
    this.listener = null
  }
  fire(): void {
    this.listener?.call(this as unknown as MediaQueryList, this as unknown as MediaQueryListEvent)
  }
}

function navDocument(): ChartDocument {
  const parsed = parseNavEnvelope(navWireFixture('asset_type', 'M'))
  if (parsed.capability !== 'v2') throw new Error('fixture must parse as v2')
  return parsed.document
}

let active: FakeQuery | null = null
let dprValue = 1

beforeEach(() => {
  chartState.mounts = 0
  dprValue = 1
  active = null
  vi.stubGlobal('devicePixelRatio', { valueOf: () => dprValue } as unknown as number)
  window.devicePixelRatio = 1
  vi.stubGlobal('matchMedia', vi.fn((query: string) => {
    const fake = new FakeQuery(query)
    active = fake
    return fake as unknown as MediaQueryList
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('watchDevicePixelRatio', () => {
  it('fires when the resolution query stops matching and re-arms with the new dpr', async () => {
    const seen: number[] = []
    const host = mount({
      setup() {
        watchDevicePixelRatio((dpr) => seen.push(dpr))
        return () => h('div')
      },
    })
    expect(active).not.toBeNull()
    expect(active!.value).toBe('(resolution: 1dppx)')
    // Native zoom to 200%: the old query stops matching.
    dprValue = 2
    window.devicePixelRatio = 2
    active!.fire()
    expect(seen).toEqual([2])
    // A NEW query is armed for the new resolution.
    expect(active!.value).toBe('(resolution: 2dppx)')
    dprValue = 1
    window.devicePixelRatio = 1
    active!.fire()
    expect(seen).toEqual([2, 1])
    host.unmount()
  })

  it('stops listening after unmount', async () => {
    const seen: number[] = []
    const host = mount({
      setup() {
        watchDevicePixelRatio((dpr) => seen.push(dpr))
        return () => h('div')
      },
    })
    const query = active!
    host.unmount()
    dprValue = 2
    window.devicePixelRatio = 2
    query.fire()
    expect(seen).toEqual([])
  })

  it('tolerates a missing matchMedia (non-browser environment)', () => {
    vi.stubGlobal('matchMedia', undefined)
    const seen: number[] = []
    const host = mount({
      setup() {
        watchDevicePixelRatio((dpr) => seen.push(dpr))
        return () => h('div')
      },
    })
    host.unmount()
    expect(seen).toEqual([])
  })
})

describe('EChartsNav re-initializes on a devicePixelRatio change', () => {
  it('remounts the chart (fresh painter dpr) and keeps the option contract', async () => {
    const document = navDocument()
    const interaction = ref(defaultInteraction(document))
    const wrapper = mount(EChartsNav, {
      props: { document, interaction: interaction.value },
    })
    await wrapper.vm.$nextTick()
    expect(chartState.mounts).toBe(1)
    // Native zoom changes the dpr → the painter must be re-created.
    dprValue = 2
    window.devicePixelRatio = 2
    active!.fire()
    await wrapper.vm.$nextTick()
    expect(chartState.mounts).toBe(2)
    // And back down (reset) → a third fresh painter at dpr 1.
    dprValue = 1
    window.devicePixelRatio = 1
    active!.fire()
    await wrapper.vm.$nextTick()
    expect(chartState.mounts).toBe(3)
    wrapper.unmount()
  })
})
