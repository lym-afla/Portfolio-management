import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import Navigation from '@/components/Navigation.vue'
import { workspaceNavigation } from '@/components/workspace/navigation'
const mobile = vi.hoisted(() => ({ value: false }))
vi.mock('vuetify', async () => {
  const { computed } = await import('vue')
  return { useDisplay: () => ({ mdAndUp: computed(() => !mobile.value) }) }
})
const Drawer = defineComponent({
  props: ['modelValue', 'temporary', 'permanent', 'rail', 'expandOnHover'],
  template:
    '<nav v-if="modelValue" :data-rail="rail" :data-temporary="temporary" :data-expand-on-hover="expandOnHover"><slot /><slot name="append" /></nav>',
})
const Item = defineComponent({
  props: ['to', 'title'],
  template:
    '<a v-if="to" :href="to">{{ title }}<slot /></a><button v-else>{{ title }}<slot /></button>',
})
async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: workspaceNavigation.map((i) => ({
      path: i.to,
      component: { template: '<div />' },
    })),
  })
  await router.push('/dashboard')
  await router.isReady()
  const wrapper = mount(Navigation, {
    attachTo: document.body,
    global: {
      plugins: [router],
      stubs: {
        VNavigationDrawer: Drawer,
        VListItem: Item,
        VList: { template: '<div><slot /></div>' },
        VListSubheader: { template: '<h3><slot /></h3>' },
        VBtn: { template: '<button><slot /></button>' },
        VIcon: true,
        VDivider: true,
      },
    },
  })
  return { wrapper, router }
}
// The desktop rail is compact by default and only expands while a pointer or
// keyboard focus is inside it; it must collapse after BOTH leave.
function drawer(wrapper) {
  return wrapper.get('nav')
}
async function hover(wrapper, on) {
  await drawer(wrapper).trigger(on ? 'mouseenter' : 'mouseleave')
  await flushPromises()
}
async function focusNav(wrapper, on) {
  if (on) {
    drawer(wrapper).element.dispatchEvent(
      new FocusEvent('focusin', { bubbles: true })
    )
  } else {
    drawer(wrapper).element.dispatchEvent(
      new FocusEvent('focusout', { bubbles: true })
    )
  }
  await flushPromises()
}
beforeEach(() => {
  mobile.value = false
})
it('renders a compact expand-on-hover desktop rail with grouped labels while expanded', async () => {
  const { wrapper } = await setup()
  const nav = drawer(wrapper)
  expect(nav.attributes('data-rail')).toBe('true')
  expect(nav.attributes('data-expand-on-hover')).toBe('true')
  // The section grouping stays in the tree collapsed and expanded (stable
  // structure — the compact look is CSS, not conditional rendering), and
  // every route stays reachable with its label as the accessible name.
  expect(wrapper.find('h3').exists()).toBe(true)
  const hrefs = wrapper.findAll('a').map((a) => a.attributes('href'))
  expect(hrefs).toEqual(workspaceNavigation.map((i) => i.to))
  expect(wrapper.get('a[href="/dashboard"]').attributes('aria-current')).toBe(
    'page'
  )
  // Pointer enters: the rail expands (visual grouping comes back).
  await hover(wrapper, true)
  expect(wrapper.vm.navExpanded).toBe(true)
  expect(wrapper.text()).toContain('Positions')
  expect(wrapper.text()).toContain('Data')
  // Both leave: it collapses again.
  await hover(wrapper, false)
  expect(wrapper.vm.navExpanded).toBe(false)
  expect(wrapper.find('h3').exists()).toBe(true)
  wrapper.unmount()
})
it('expands on keyboard focus and only collapses after focus and pointer both leave', async () => {
  const { wrapper } = await setup()
  await focusNav(wrapper, true)
  expect(wrapper.vm.navExpanded).toBe(true)
  // The pointer passing through and leaving must NOT collapse while the
  // keyboard focus stays inside.
  await hover(wrapper, true)
  await hover(wrapper, false)
  expect(wrapper.vm.navExpanded).toBe(true)
  await focusNav(wrapper, false)
  expect(wrapper.vm.navExpanded).toBe(false)
  wrapper.unmount()
})
it('opens temporary mobile navigation, closes on selection and restores focus', async () => {
  mobile.value = true
  const { wrapper, router } = await setup()
  expect(wrapper.find('nav').exists()).toBe(false)
  const trigger = wrapper.get('[aria-label="Open navigation"]')
  await trigger.trigger('click')
  expect(wrapper.get('nav').attributes('data-temporary')).toBe('true')
  // The mobile drawer shows the section grouping (explicit toggle).
  expect(wrapper.text()).toContain('Positions')
  await wrapper.get('a[href="/summary"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/summary')
  expect(wrapper.find('nav').exists()).toBe(false)
  expect(document.activeElement).toBe(trigger.element)
  await trigger.trigger('click')
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  await flushPromises()
  expect(wrapper.find('nav').exists()).toBe(false)
  expect(document.activeElement).toBe(trigger.element)
  wrapper.unmount()
})
