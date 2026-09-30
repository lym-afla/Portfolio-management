import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'

describe('WorkspaceSection', () => {
  it('names the section from its visible heading and preserves content and actions', () => {
    const wrapper = mount(WorkspaceSection, {
      props: { headingId: 'allocation', title: 'Allocation', description: 'Portfolio composition' },
      slots: { default: '<p>Cash is included</p>', actions: '<button>View details</button>' },
    })
    expect(wrapper.get('section').attributes('aria-labelledby')).toBe('allocation')
    expect(wrapper.get('h2#allocation').text()).toBe('Allocation')
    expect(wrapper.text()).toContain('Cash is included')
    expect(wrapper.get('button').text()).toBe('View details')
    wrapper.unmount()
  })
})
