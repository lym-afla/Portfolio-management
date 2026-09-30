import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import { workspaceHeadingKey } from '@/components/workspace/types'

describe('WorkspacePage', () => {
  it('provides one page heading, preserves context and releases shell heading registration', () => {
    const release = vi.fn()
    const register = vi.fn(() => release)
    const wrapper = mount(WorkspacePage, {
      props: { title: 'Dashboard', description: 'Portfolio overview' },
      slots: { context: '<p>Main account · 8 September</p>', default: '<p>Portfolio data</p>', actions: '<button>Export</button>' },
      global: { provide: { [workspaceHeadingKey as symbol]: register }, stubs: { VDefaultsProvider: { template: '<div><slot /></div>' } } },
    })
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toBe('Dashboard')
    expect(wrapper.text()).toContain('Main account')
    expect(wrapper.text()).toContain('Portfolio data')
    expect(register).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(release).toHaveBeenCalledOnce()
  })
})
