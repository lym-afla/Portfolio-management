// D4 Task 2 — WorkspaceTableToolbar is a layout/intent component: labelled
// search + rows selector + slots, emitting one update:query intent per
// change. It never fetches, debounces or formats values itself.
import { beforeAll, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'

// jsdom has no visualViewport; Vuetify's overlay location strategy needs it
// to open menus in component tests.
beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

const vuetify = createVuetify({ components, directives })

const mountToolbar = (props: Record<string, unknown> = {}) =>
  mount(WorkspaceTableToolbar, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: {
      query: { search: '', page: 1, itemsPerPage: 25 },
      searchLabel: 'Search positions',
      rowsPerPageOptions: [10, 25, 50],
      ...props,
    },
  })

describe('WorkspaceTableToolbar', () => {
  it('renders a labelled search field and a labelled rows-per-page selector', () => {
    const wrapper = mountToolbar({ searchPlaceholder: 'Search by name or type' })
    expect(wrapper.text()).toContain('Search positions')
    expect(wrapper.text()).toContain('Rows per page')
    expect(wrapper.find('input[aria-label="Search positions"]').exists()).toBe(true)
    expect(wrapper.find('input').attributes('placeholder')).toBe('Search by name or type')
    wrapper.unmount()
  })

  it('emits exactly one update:query intent per search input', async () => {
    const wrapper = mountToolbar()
    const input = wrapper.find('input')
    await input.setValue('IBM')
    const emissions = wrapper.emitted('update:query')
    expect(emissions).toHaveLength(1)
    expect(emissions![0]).toEqual([{ search: 'IBM' }])
    wrapper.unmount()
  })

  it('emits exactly one update:query intent when rows-per-page changes', async () => {
    const wrapper = mountToolbar()
    const rows = wrapper.find('.workspace-table-toolbar__rows')
    await rows.find('.v-field').trigger('mousedown')
    await rows.find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    const options = document.querySelectorAll('.v-overlay--active .v-list-item')
    expect(options.length).toBe(3)
    ;(options[2] as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const emissions = wrapper.emitted('update:query')
    expect(emissions).toHaveLength(1)
    expect(emissions![0]).toEqual([{ itemsPerPage: 50 }])
    wrapper.unmount()
  })

  it('exposes slots for filters, columns and actions', () => {
    const wrapper = mount(WorkspaceTableToolbar, {
      global: { plugins: [vuetify] },
      props: { query: { search: '', page: 1, itemsPerPage: 25 }, searchLabel: 'Search', rowsPerPageOptions: [25] },
      slots: {
        filters: '<div data-testid="slot-filters">filters</div>',
        columns: '<div data-testid="slot-columns">columns</div>',
        actions: '<div data-testid="slot-actions">actions</div>',
      },
    })
    expect(wrapper.find('[data-testid="slot-filters"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="slot-columns"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="slot-actions"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
