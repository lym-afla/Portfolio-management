import { expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ProfileSettings from '@/views/profile/ProfileSettings.vue'
import { generateVuetifyStubs } from '../test-utils'
const { changeContext, updateUserSettings } = vi.hoisted(() => ({
  changeContext: vi.fn().mockResolvedValue(undefined),
  updateUserSettings: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('@/stores/portfolioContext', () => ({
  usePortfolioContextStore: () => ({
    changeContext,
    reconcileContext: vi.fn(),
    committed: { effectiveCurrentDate: '2026-09-08' },
  }),
}))
vi.mock('@/services/api', () => ({
  updateUserSettings,
  getUserSettings: vi.fn(async () => ({
    default_currency: 'USD',
    digits: 2,
    selected_account_type: 'all',
    selected_account_id: null,
  })),
  getSettingsChoices: vi.fn(async () => ({
    currency_choices: [
      ['USD', 'Dollar'],
      ['EUR', 'Euro'],
    ],
    frequency_choices: [],
    timeline_choices: [],
    nav_breakdown_choices: [],
    // Backend-faithful available choices: the injected broker selection can
    // only be saved when it matches a real selectable option.
    account_choices: [
      ['General', [['All accounts', { type: 'all', id: null }]]],
      ['__SEPARATOR__', '__SEPARATOR__'],
      ['Brokers', [['Test Broker', { type: 'broker', id: 4, display_name: 'All Test Broker accounts' }]]],
    ],
  })),
}))
it('sends profile financial preferences through the committed-context queue', async () => {
  const wrapper = shallowMount(ProfileSettings, {
    global: {
      stubs: {
        ...generateVuetifyStubs(),
        VProgressCircular: true,
        VDivider: true,
        VListSubheader: true,
      },
    },
  })
  await flushPromises()
  Object.assign(wrapper.vm.settingsForm, {
    default_currency: 'EUR',
    digits: 4,
    selected_account: { type: 'broker', id: 4 },
  })
  await wrapper.vm.saveSettings()
  expect(changeContext).toHaveBeenCalledWith({
    accountSelection: { type: 'broker', id: 4 },
    currency: 'EUR',
    digits: 4,
    effectiveCurrentDate: '2026-09-08',
  })
  const preferences = updateUserSettings.mock.calls[0][0]
  for (const key of [
    'selected_account_type',
    'selected_account_id',
    'default_currency',
    'digits',
  ])
    expect(preferences).not.toHaveProperty(key)
  wrapper.unmount()
})
