import { shallowMount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import SettingsDialog from '@/components/SettingsDialog.vue'
vi.mock('@/stores/portfolioContext', () => ({
  usePortfolioContextStore: () => ({
    canRead: true,
    isReady: true,
    isTransitioning: false,
    currencyChoices: [{ value: 'USD', text: 'Dollar' }],
    committed: {
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 2,
    },
  }),
}))
it('offers a named precision preference and preserves confirmed settings when saving zero', async () => {
  const requestChange = vi.fn(async () => {})
  const wrapper = shallowMount(SettingsDialog, {
    global: {
      renderStubDefaultSlot: true,
      stubs: {
        VTextField: true,
        VSelect: true,
        VDialog: true,
        VCard: true,
        VCardTitle: true,
        VCardText: true,
        VCardActions: true,
        VForm: true,
        VBtn: true,
        VIcon: true,
        VSpacer: true,
        VAlert: true,
      },
    },
    props: { preferencesOnly: true, requestChange },
  })
  expect(wrapper.get('[aria-label="Display preferences"]').exists()).toBe(true)
  await wrapper.vm.openDialog()
  expect(
    wrapper.findAll('v-text-field-stub').map((w) => w.attributes('label'))
  ).toEqual(['Number of digits'])
  expect(wrapper.find('v-dialog-stub').attributes('aria-labelledby')).toBe(
    'display-preferences-heading'
  )
  wrapper.vm.formData.digits = 0
  await wrapper.vm.saveSettings()
  await flushPromises()
  expect(requestChange).toHaveBeenCalledExactlyOnceWith({ digits: 0 })
})
it('retains the preference dialog and error on rejected save', async () => {
  const wrapper = shallowMount(SettingsDialog, {
    global: {
      renderStubDefaultSlot: true,
      stubs: {
        VTextField: true,
        VSelect: true,
        VDialog: true,
        VCard: true,
        VCardTitle: true,
        VCardText: true,
        VCardActions: true,
        VForm: true,
        VBtn: true,
        VIcon: true,
        VSpacer: true,
        VAlert: true,
      },
    },
    props: {
      preferencesOnly: true,
      requestChange: async () => {
        throw new Error('Denied')
      },
    },
  })
  await wrapper.vm.openDialog()
  await wrapper.vm.saveSettings()
  await flushPromises()
  expect(wrapper.vm.dialog).toBe(true)
  expect(wrapper.vm.errors.general).toEqual(['Denied'])
})
