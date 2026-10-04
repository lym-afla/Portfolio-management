// Profile Settings account-selection preservation regressions, driven through
// the REAL Vuetify VSelect (no label-simplifying stub): the settings response
// is the authority for the form's saved identity, an identity absent from the
// choices must stay preserved and unresolved (safe "Unavailable"/"All
// accounts" display, persistent explanation, blocked saving), and only actual
// selectable option values may enter the form identity. The fixtures mirror
// the backend's prepare_account_choices structure exactly (General/Your
// Accounts/Brokers/Account Groups sections with __SEPARATOR__ rows).
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import ProfileSettings from '@/views/profile/ProfileSettings.vue'
import { getUserSettings, updateUserSettings, getSettingsChoices } from '@/services/api'

// Backend-faithful prepare_account_choices output, identical to the header
// label spec's fixture so both surfaces see the same real option shapes.
const BACKEND_ACCOUNT_CHOICES = [
  ['General', [['All accounts', { type: 'all', id: null }]]],
  ['__SEPARATOR__', '__SEPARATOR__'],
  [
    'Your Accounts',
    [
      ['First', { type: 'account', id: 1, display_name: 'First Broker – First account' }],
      ['Second', { type: 'account', id: 2, display_name: 'Second Broker – Second account' }],
    ],
  ],
  ['__SEPARATOR__', '__SEPARATOR__'],
  ['Brokers', [['First Broker', { type: 'broker', id: 3, display_name: 'All First Broker accounts' }]]],
  ['__SEPARATOR__', '__SEPARATOR__'],
  ['Account Groups', [['Long Term', { type: 'group', id: 4, display_name: 'Long Term' }]]],
]

const SAVED_UNAVAILABLE_MESSAGE =
  'Your saved account selection is unavailable. Choose an available account selection before saving.'
const CHOICES_UNAVAILABLE_MESSAGE =
  'Account choices are unavailable. Reload settings before saving.'

// The live header context deliberately carries a DIFFERENT selection ({account, 1})
// than the saved settings below: the form must adopt the settings response,
// never the store's committed selection.
const { changeContext } = vi.hoisted(() => ({ changeContext: vi.fn() }))
vi.mock('@/stores/portfolioContext', () => ({
  usePortfolioContextStore: () => ({
    changeContext,
    committed: {
      effectiveCurrentDate: '2026-09-08',
      accountSelection: { type: 'account', id: 1 },
    },
  }),
}))

const state = { settings: {}, choices: {} }

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getUserSettings: vi.fn(async () => state.settings),
    getSettingsChoices: vi.fn(async () => state.choices),
    updateUserSettings: vi.fn(async () => ({ success: true })),
  }
})

const fullSettings = {
  default_currency: 'USD',
  use_default_currency_where_relevant: true,
  chart_frequency: 'M',
  chart_timeline: 'YTD',
  NAV_barchart_default_breakdown: 'none',
  digits: 2,
  selected_account_type: 'account',
  selected_account_id: 2,
}
const fullChoices = {
  currency_choices: [
    ['USD', 'US Dollar'],
    ['EUR', 'Euro'],
  ],
  frequency_choices: [['M', 'Monthly']],
  timeline_choices: [['YTD', 'Year to date']],
  nav_breakdown_choices: [['none', 'No breakdown']],
  account_choices: BACKEND_ACCOUNT_CHOICES,
}

const vuetify = createVuetify({ components, directives })

// jsdom has no visualViewport; Vuetify's overlay location strategy needs it.
beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

beforeEach(() => {
  vi.clearAllMocks()
  // Vuetify's teleported snackbar overlays can outlive a previous test's
  // unmount in the shared document.body; a clean body keeps pageText()
  // assertions about success/error messages scoped to the current test.
  document.body.replaceChildren()
  state.settings = structuredClone(fullSettings)
  state.choices = structuredClone(fullChoices)
  updateUserSettings.mockResolvedValue({ success: true })
  changeContext.mockResolvedValue(undefined)
})

const mountSettings = async (mountOverrides = {}) => {
  const wrapper = mount(ProfileSettings, {
    global: {
      plugins: [vuetify],
      stubs: { AccountGroupManager: true, BrokerTokenManager: true },
    },
    attachTo: document.body,
    ...mountOverrides,
  })
  await flushPromises()
  return wrapper
}

const accountSelect = (wrapper) =>
  wrapper
    .findAllComponents({ name: 'VSelect' })
    .find((select) => select.props('label') === 'Default Account Selection')

const visibleLabel = (wrapper) => accountSelect(wrapper).find('.v-select__selection').text()

const inputValue = (wrapper) => accountSelect(wrapper).find('input').element.value

const fieldMessages = (wrapper) =>
  accountSelect(wrapper)
    .findAll('.v-messages__message')
    .map((message) => message.text())

const availableOptionTitles = (wrapper) =>
  accountSelect(wrapper)
    .props('items')
    .filter((item) => item.type === 'option')
    .map((item) => item.title)

const saveButton = (wrapper) =>
  wrapper.findAll('button').find((button) => button.text().includes('Save Settings'))

const saveIsDisabled = (wrapper) => saveButton(wrapper).attributes('disabled') !== undefined

const pageText = () => document.body.textContent

const expectNoRawObject = (wrapper, context) => {
  expect(pageText(), `${context}: no raw object label`).not.toContain('[object Object]')
  expect(pageText(), `${context}: no raw JSON label`).not.toContain('"type"')
}

describe('ProfileSettings saved-identity display (real Vuetify select)', () => {
  it('resolves a matching All accounts identity with saving enabled', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'all', selected_account_id: null }
    const wrapper = await mountSettings()
    expect(visibleLabel(wrapper)).toBe('All accounts')
    expect(inputValue(wrapper)).toBe('All accounts')
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'all', id: null })
    expect(fieldMessages(wrapper)).toEqual([])
    expect(saveIsDisabled(wrapper)).toBe(false)
    expectNoRawObject(wrapper, 'all identity')
    wrapper.unmount()
  })

  it('resolves matching named account, broker and group identities', async () => {
    const wrapper = await mountSettings()
    expect(visibleLabel(wrapper)).toBe('Second Broker – Second account')
    expect(inputValue(wrapper)).toBe('Second Broker – Second account')
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'account', id: 2 })
    expect(fieldMessages(wrapper)).toEqual([])
    expect(saveIsDisabled(wrapper)).toBe(false)
    wrapper.unmount()

    state.settings = { ...fullSettings, selected_account_type: 'broker', selected_account_id: 3 }
    const brokerWrapper = await mountSettings()
    expect(visibleLabel(brokerWrapper)).toBe('All First Broker accounts')
    expect(inputValue(brokerWrapper)).toBe('All First Broker accounts')
    brokerWrapper.unmount()

    state.settings = { ...fullSettings, selected_account_type: 'group', selected_account_id: 4 }
    const groupWrapper = await mountSettings()
    expect(visibleLabel(groupWrapper)).toBe('Long Term')
    expect(inputValue(groupWrapper)).toBe('Long Term')
    groupWrapper.unmount()
  })

  it('preserves a saved identity missing from choices as Unavailable with saving blocked', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'account', selected_account_id: 99 }
    const wrapper = await mountSettings()
    expect(wrapper.vm.settingsForm.selected_account,
      'the saved identity is kept exactly as returned, never replaced by the store or All accounts')
      .toEqual({ type: 'account', id: 99 })
    expect(visibleLabel(wrapper)).toBe('Unavailable')
    expect(inputValue(wrapper)).toBe('Unavailable')
    expect(fieldMessages(wrapper)).toEqual([SAVED_UNAVAILABLE_MESSAGE])
    expect(saveIsDisabled(wrapper)).toBe(true)
    expect(availableOptionTitles(wrapper)).toEqual([
      'All accounts',
      'First Broker – First account',
      'Second Broker – Second account',
      'All First Broker accounts',
      'Long Term',
    ])
    expect(visibleLabel(wrapper),
      'the store committed selection ({account, 1}) is never adopted').not.toBe('First Broker – First account')
    expectNoRawObject(wrapper, 'missing saved identity')
    wrapper.unmount()
  })

  it('shows All accounts honestly but unresolved when choices are empty', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'all', selected_account_id: null }
    state.choices = { ...fullChoices, account_choices: [] }
    const wrapper = await mountSettings()
    expect(visibleLabel(wrapper)).toBe('All accounts')
    expect(inputValue(wrapper)).toBe('All accounts')
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'all', id: null })
    expect(fieldMessages(wrapper)).toEqual([CHOICES_UNAVAILABLE_MESSAGE])
    expect(saveIsDisabled(wrapper)).toBe(true)
    expectNoRawObject(wrapper, 'empty choices with all identity')
    wrapper.unmount()
  })

  it('treats a malformed saved identity as unresolved and never defaults to All accounts', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'dragon', selected_account_id: 7 }
    const wrapper = await mountSettings()
    expect(wrapper.vm.settingsForm.selected_account).toBeNull()
    expect(visibleLabel(wrapper)).toBe('Unavailable')
    expect(inputValue(wrapper)).toBe('Unavailable')
    expect(fieldMessages(wrapper)).toEqual([SAVED_UNAVAILABLE_MESSAGE])
    expect(saveIsDisabled(wrapper)).toBe(true)
    expectNoRawObject(wrapper, 'malformed saved identity')
    wrapper.unmount()

    state.settings = { ...fullSettings }
    delete state.settings.selected_account_type
    delete state.settings.selected_account_id
    const missingWrapper = await mountSettings()
    expect(missingWrapper.vm.settingsForm.selected_account).toBeNull()
    expect(visibleLabel(missingWrapper)).toBe('Unavailable')
    expect(fieldMessages(missingWrapper)).toEqual([SAVED_UNAVAILABLE_MESSAGE])
    missingWrapper.unmount()
  })

  it('keeps the loading state until both responses land, then resolves from the response', async () => {
    let releaseSettings
    getUserSettings.mockImplementationOnce(
      () => new Promise((resolve) => { releaseSettings = resolve })
    )
    const wrapper = mount(ProfileSettings, {
      global: {
        plugins: [vuetify],
        stubs: { AccountGroupManager: true, BrokerTokenManager: true },
      },
      attachTo: document.body,
    })
    await flushPromises()
    expect(wrapper.find('.v-progress-circular').exists(), 'loading spinner shown').toBe(true)
    expect(wrapper.find('form').exists(), 'form hidden while loading').toBe(false)
    releaseSettings(structuredClone(fullSettings))
    await flushPromises()
    expect(wrapper.find('.v-progress-circular').exists()).toBe(false)
    expect(wrapper.vm.settingsForm.selected_account,
      'identity adopted from the settings response, not the store ({account, 1})')
      .toEqual({ type: 'account', id: 2 })
    expect(visibleLabel(wrapper)).toBe('Second Broker – Second account')
    expect(saveIsDisabled(wrapper)).toBe(false)
    wrapper.unmount()
  })

  it('blocks saving after a load failure instead of offering a replacement save', async () => {
    getSettingsChoices.mockRejectedValueOnce(new Error('Synthetic choices failure'))
    const wrapper = await mountSettings()
    expect(wrapper.vm.settingsForm.selected_account).toBeNull()
    expect(saveIsDisabled(wrapper)).toBe(true)
    expect(fieldMessages(wrapper)).toEqual([])
    expect(pageText()).toContain('Failed to load settings. Please try again.')
    await wrapper.vm.saveSettings()
    await flushPromises()
    expect(updateUserSettings).not.toHaveBeenCalled()
    expect(changeContext).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('ProfileSettings save guarding and explicit selection', () => {
  const selectIdentity = async (wrapper, type, id) => {
    const option = accountSelect(wrapper)
      .props('items')
      .find((item) => item.type === 'option' && item.value.type === type && item.value.id === id)
    expect(option, `selectable ${type} ${id} option exists`).toBeDefined()
    accountSelect(wrapper).vm.$emit('update:modelValue', option.value)
    await flushPromises()
  }

  it('makes zero writes when another preference is saved while unresolved', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'account', selected_account_id: 99 }
    const wrapper = await mountSettings()
    wrapper.vm.settingsForm.chart_frequency = 'W'
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(updateUserSettings).not.toHaveBeenCalled()
    expect(changeContext).not.toHaveBeenCalled()
    await wrapper.vm.saveSettings()
    await flushPromises()
    expect(updateUserSettings).not.toHaveBeenCalled()
    expect(changeContext).not.toHaveBeenCalled()
    expect(wrapper.vm.settingsForm.chart_frequency, 'the unrelated edit is preserved').toBe('W')
    wrapper.unmount()
  })

  it('saves an explicitly selected account with its identity through the context queue', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'account', selected_account_id: 99 }
    const wrapper = await mountSettings()
    await selectIdentity(wrapper, 'account', 2)
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'account', id: 2 })
    expect(visibleLabel(wrapper)).toBe('Second Broker – Second account')
    expect(inputValue(wrapper)).toBe('Second Broker – Second account')
    expect(fieldMessages(wrapper), 'the availability warning clears after a real selection')
      .toEqual([])
    wrapper.vm.settingsForm.digits = 5
    saveButton(wrapper).trigger('click')
    await flushPromises()
    expect(updateUserSettings).toHaveBeenCalledTimes(1)
    const preferences = updateUserSettings.mock.calls[0][0]
    for (const key of [
      'selected_account',
      'selected_account_type',
      'selected_account_id',
      'default_currency',
      'digits',
    ])
      expect(preferences).not.toHaveProperty(key)
    expect(changeContext).toHaveBeenCalledWith({
      accountSelection: { type: 'account', id: 2 },
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 5,
    })
    expect(pageText()).toContain('Settings saved successfully')
    expectNoRawObject(wrapper, 'explicit selection save')
    wrapper.unmount()
  })

  it('saves an explicitly selected All accounts identity through the context queue', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'account', selected_account_id: 99 }
    const wrapper = await mountSettings()
    await selectIdentity(wrapper, 'all', null)
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'all', id: null })
    expect(visibleLabel(wrapper)).toBe('All accounts')
    expect(fieldMessages(wrapper)).toEqual([])
    saveButton(wrapper).trigger('click')
    await flushPromises()
    expect(changeContext).toHaveBeenCalledWith({
      accountSelection: { type: 'all', id: null },
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 2,
    })
    expect(pageText()).toContain('Settings saved successfully')
    wrapper.unmount()
  })

  it('never accepts the safe display string or an unavailable identity as a selection', async () => {
    state.settings = { ...fullSettings, selected_account_type: 'account', selected_account_id: 99 }
    const wrapper = await mountSettings()
    accountSelect(wrapper).vm.$emit('update:modelValue', 'Unavailable')
    await flushPromises()
    expect(wrapper.vm.settingsForm.selected_account,
      'the safe label string never enters the form identity').toEqual({ type: 'account', id: 99 })
    accountSelect(wrapper).vm.$emit('update:modelValue', { type: 'account', id: 99 })
    await flushPromises()
    expect(wrapper.vm.settingsForm.selected_account,
      'a non-selectable identity never enters the form identity').toEqual({ type: 'account', id: 99 })
    wrapper.unmount()
  })

  it('blocks duplicate submissions while a save is pending', async () => {
    let releaseSave
    updateUserSettings.mockImplementationOnce(
      () => new Promise((resolve) => { releaseSave = resolve })
    )
    const wrapper = await mountSettings()
    const firstSave = wrapper.vm.saveSettings()
    const secondSave = wrapper.vm.saveSettings()
    releaseSave({ success: true })
    await Promise.all([firstSave, secondSave])
    await flushPromises()
    expect(updateUserSettings).toHaveBeenCalledTimes(1)
    expect(changeContext).toHaveBeenCalledTimes(1)
    expect(pageText()).toContain('Settings saved successfully')
    wrapper.unmount()
  })

  it('retains edits and the selection after a rejected profile write, then saves the retry', async () => {
    updateUserSettings.mockResolvedValueOnce({
      success: false,
      errors: { digits: ['Synthetic digits rejection'] },
    })
    const wrapper = await mountSettings()
    wrapper.vm.settingsForm.digits = 5
    await wrapper.vm.saveSettings()
    await flushPromises()
    expect(updateUserSettings).toHaveBeenCalledTimes(1)
    expect(changeContext, 'a rejected profile write must not reach the context queue')
      .not.toHaveBeenCalled()
    expect(pageText()).toContain('Please correct the errors in the form.')
    expect(pageText()).toContain('Synthetic digits rejection')
    expect(pageText()).not.toContain('Settings saved successfully')
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'account', id: 2 })
    expect(wrapper.vm.settingsForm.digits).toBe(5)
    updateUserSettings.mockResolvedValue({ success: true })
    await wrapper.vm.saveSettings()
    await flushPromises()
    expect(updateUserSettings).toHaveBeenCalledTimes(2)
    expect(changeContext).toHaveBeenCalledTimes(1)
    expect(changeContext).toHaveBeenCalledWith({
      accountSelection: { type: 'account', id: 2 },
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 5,
    })
    expect(pageText()).toContain('Settings saved successfully')
    wrapper.unmount()
  })

  it('surfaces a rejected context write without success and retains the selection', async () => {
    changeContext.mockRejectedValueOnce(new Error('Synthetic context denied'))
    const wrapper = await mountSettings()
    await wrapper.vm.saveSettings()
    await flushPromises()
    expect(updateUserSettings).toHaveBeenCalledTimes(1)
    expect(changeContext).toHaveBeenCalledTimes(1)
    expect(pageText()).toContain('Failed to save settings. Please try again.')
    expect(pageText()).not.toContain('Settings saved successfully')
    expect(wrapper.vm.settingsForm.selected_account).toEqual({ type: 'account', id: 2 })
    expect(saveIsDisabled(wrapper), 'Save re-enables after the failed sequence ends').toBe(false)
    wrapper.unmount()
  })
})
