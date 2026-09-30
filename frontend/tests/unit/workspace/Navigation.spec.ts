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
  props: ['modelValue', 'temporary', 'permanent', 'rail'],
  template:
    '<nav v-if="modelValue" :data-rail="rail" :data-temporary="temporary"><slot /><slot name="append" /></nav>',
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
beforeEach(() => {
  mobile.value = false
})
it('uses labeled desktop navigation with grouped positions and current page semantics', async () => {
  const { wrapper } = await setup()
  expect(wrapper.get('nav').attributes('data-rail')).toBe('false')
  expect(wrapper.text()).toContain('Overview')
  expect(wrapper.text()).toContain('Performance')
  expect(wrapper.text()).toContain('Positions')
  expect(wrapper.text()).toContain('Data')
  expect(wrapper.get('a[href="/dashboard"]').attributes('aria-current')).toBe(
    'page'
  )
  expect(wrapper.findAll('a').map((a) => a.attributes('href'))).toEqual(
    workspaceNavigation.map((i) => i.to)
  )
  wrapper.unmount()
})
it('opens temporary mobile navigation, closes on selection and restores focus', async () => {
  mobile.value = true
  const { wrapper, router } = await setup()
  expect(wrapper.find('nav').exists()).toBe(false)
  const trigger = wrapper.get('[aria-label="Open navigation"]')
  await trigger.trigger('click')
  expect(wrapper.get('nav').attributes('data-temporary')).toBe('true')
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
