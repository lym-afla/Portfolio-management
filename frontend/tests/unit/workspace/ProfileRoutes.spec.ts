// D5 Task 4 — profile/auth route contracts: navigation and settings
// sections, original settings payloads and the context-affecting save,
// login/register labels/autocomplete/redirects, and the typed-DELETE account
// deletion requirement. Auth/session/redirect logic is asserted unchanged.
import { beforeEach, beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { readFileSync } from 'node:fs'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'

const api = vi.hoisted(() => ({
  getUserSettings: vi.fn(),
  getSettingsChoices: vi.fn(),
  updateUserSettings: vi.fn(),
  getAccountGroups: vi.fn(),
  getBrokerTokens: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  getUserProfile: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const vuetify = createVuetify({ components, directives })

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

afterEach(() => {
  document.body.innerHTML = ''
})

const settingsFixture = {
  default_currency: 'USD',
  use_default_currency_where_relevant: true,
  chart_frequency: 'M',
  chart_timeline: 'YTD',
  NAV_barchart_default_breakdown: 'none',
  digits: 2,
  selected_account_type: 'all',
  selected_account_id: null,
}
const choicesFixture = {
  currency_choices: [['USD', 'US Dollar'], ['EUR', 'Euro']],
  frequency_choices: [['M', 'Monthly']],
  timeline_choices: [['YTD', 'Year to date']],
  nav_breakdown_choices: [['none', 'No breakdown']],
  // Backend-faithful prepare_account_choices output (PR #55 shape): the
  // saved 'all' selection must resolve against an available option before
  // the pending-save guards allow saveSettings to run.
  account_choices: [['General', [['All accounts', { type: 'all', id: null }]]]],
}

async function mountAuth(): Promise<{ wrapper: VueWrapper; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'Login', component: (await import('@/views/LoginPage.vue')).default },
      { path: '/register', name: 'Register', component: (await import('@/views/RegisterPage.vue')).default },
      { path: '/profile', name: 'Profile', component: { template: '<div>profile-target</div>' } },
    ],
  })
  router.push('/login')
  await router.isReady()
  const wrapper = mount({ template: '<router-view />' }, {
    global: {
      plugins: [vuetify, createPinia(), router],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

async function mountProfile(path: string): Promise<{ wrapper: VueWrapper; router: Router }> {
  const ProfileLayout = (await import('@/views/profile/ProfileLayout.vue')).default
  const ProfilePage = (await import('@/views/profile/ProfilePage.vue')).default
  const ProfileEdit = (await import('@/views/profile/ProfileEdit.vue')).default
  const ProfileSettings = (await import('@/views/profile/ProfileSettings.vue')).default
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/profile',
      component: ProfileLayout,
      children: [
        { path: '', name: 'Profile', component: ProfilePage },
        { path: 'edit', name: 'ProfileEdit', component: ProfileEdit },
        { path: 'settings', name: 'ProfileSettings', component: ProfileSettings },
      ],
    }],
  })
  router.push(path)
  await router.isReady()
  const pinia = createPinia()
  const contextStore = await usePortfolioContextStore(pinia).reconcileContext().then(() => usePortfolioContextStore(pinia))
  const wrapper = mount({ template: '<router-view />' }, {
    attachTo: document.body,
    global: {
      plugins: [vuetify, pinia, router],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        AccountGroupManager: { template: '<section aria-label="Account groups" />' },
        BrokerTokenManager: { template: '<section aria-label="Broker connections" />' },
      },
    },
  })
  await flushPromises()
  return { wrapper, router, contextStore }
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
  api.getUserSettings.mockResolvedValue({ ...settingsFixture })
  api.getSettingsChoices.mockResolvedValue({ ...choicesFixture })
  api.updateUserSettings.mockResolvedValue({ success: true })
  api.getAccountGroups.mockResolvedValue({ groups: {}, available_accounts: [] })
  api.getBrokerTokens.mockResolvedValue({ tinkoff_tokens: [], ib_tokens: [], bybit_tokens: [], okx_tokens: [] })
  api.getUserProfile.mockResolvedValue({ username: 'fixture-user', email: 'fixture@example.invalid', first_name: 'Fixture', last_name: 'User' })
})

describe('/profile layout', () => {
  it('renders one Profile heading with navigation to details and settings', async () => {
    const { wrapper } = await mountProfile('/profile')
    const headings = wrapper.findAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0].text()).toBe('Profile')
    const links = wrapper.findAll('a').map((a) => a.attributes('href'))
    expect(links).toContain('/profile')
    expect(links).toContain('/profile/settings')
    expect(wrapper.text()).toContain('Logout')
    expect(wrapper.text()).toContain('User details')
  })

  it('keeps the typed DELETE requirement before account deletion', async () => {
    const { wrapper } = await mountProfile('/profile')
    await wrapper.findAll('button').find((b) => b.text().includes('Delete Account'))!.trigger('click')
    await flushPromises()
    const dialog = document.querySelector('.v-overlay--active [role="dialog"], .v-dialog')
    expect(dialog).toBeTruthy()
    const dialogText = document.body.textContent ?? ''
    expect(dialogText).toContain("Type 'DELETE' to confirm")
    const confirmButton = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Delete Account' && b.closest('.v-overlay--active'))
    expect(confirmButton).toBeTruthy()
    expect(confirmButton!.hasAttribute('disabled')).toBe(true)
  })
})

describe('/profile/settings', () => {
  it('saves the original payload shape and drives the context change', async () => {
    const changeContextSpy = vi.fn()
    const { wrapper, contextStore } = await mountProfile('/profile/settings')
    contextStore.changeContext = changeContextSpy
    await flushPromises()
    expect(api.getUserSettings).toHaveBeenCalled()
    expect(api.getSettingsChoices).toHaveBeenCalled()
    expect(wrapper.text()).toContain('User Settings')
    expect(wrapper.text()).toContain('Default currency')
    expect(wrapper.text()).toContain('Number of digits')

    const save = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Save Settings')
    save!.click()
    await flushPromises()
    expect(api.updateUserSettings).toHaveBeenCalledTimes(1)
    const payload = api.updateUserSettings.mock.calls[0][0]
    // The context-owned keys (currency/digits/account selection) are stripped
    // from the wire payload; they travel through the serialized context
    // change instead, exactly as in the incumbent.
    expect(payload).not.toHaveProperty('selected_account')
    expect(payload).not.toHaveProperty('selected_account_type')
    expect(payload).not.toHaveProperty('selected_account_id')
    expect(payload).not.toHaveProperty('default_currency')
    expect(payload).not.toHaveProperty('digits')
    expect(payload.chart_frequency).toBe('M')
    expect(changeContextSpy).toHaveBeenCalledWith(expect.objectContaining({
      currency: 'USD',
      digits: 2,
      accountSelection: { type: 'all', id: null },
    }))
  })
})

describe('/login', () => {
  it('renders a narrow surface with labelled fields, autocomplete semantics and one primary submit', async () => {
    const { wrapper } = await mountAuth()
    await flushPromises()
    const text = wrapper.text()
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(text).toContain('Login')
    expect(text).toContain('Username')
    expect(text).toContain('Password')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/register"]').exists()).toBe(true)
    const submits = wrapper.findAll('button[type="submit"]')
    expect(submits).toHaveLength(1)
  })

  it('redirects to /profile after a successful login', async () => {
    api.login.mockResolvedValue({ access: 'fixture-access', refresh: 'fixture-refresh' })
    const { wrapper, router } = await mountAuth()
    await wrapper.find('input[autocomplete="username"]').setValue('fixture-user')
    await wrapper.find('input[autocomplete="current-password"]').setValue('secret')
    await wrapper.find('button[type="submit"]').trigger('submit')
    await flushPromises()
    expect(api.login).toHaveBeenCalledWith('fixture-user', 'secret')
    expect(router.currentRoute.value.path).toBe('/profile')
  })
})

describe('/register', () => {
  it('labels every field, keeps password autocomplete semantics and links to login', async () => {
    const { wrapper, router } = await mountAuth()
    await router.push('/register')
    await router.isReady()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('Register')
    expect(text).toContain('Username')
    expect(text).toContain('Email')
    expect(text).toContain('Password')
    expect(text).toContain('Confirm Password')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.findAll('input[autocomplete="new-password"]').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('a[href="/login"]').exists()).toBe(true)
    const submits = wrapper.findAll('button[type="submit"]')
    expect(submits).toHaveLength(1)
  })
})

describe('/debug-auth remains development-only', () => {
  it('registers the debug route only inside import.meta.env.DEV', () => {
    // Source-level assertion (the compiled router cannot be inspected in both
    // modes from one test): the route registration must stay inside the
    // DEV-guarded spread, as in the incumbent.
    const src = readFileSync('src/router/index.js', 'utf-8')
    expect(src).toContain("import.meta.env.DEV && AuthDebugPanel")
    expect(src).toContain("path: '/debug-auth'")
  })
})
