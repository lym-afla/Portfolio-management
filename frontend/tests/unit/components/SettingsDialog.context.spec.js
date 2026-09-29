import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsDialog from '@/components/SettingsDialog.vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configurePortfolioContextBackend } from '@/services/api/context'
vi.mock('@/services/api', () => ({
  getDashboardSettings: vi.fn(async () => ({
    settings: { default_currency: 'USD', digits: 2, table_date: '2026-09-08' },
    choices: {
      default_currency: [
        ['USD', 'Dollar'],
        ['EUR', 'Euro'],
      ],
    },
  })),
  updateDashboardSettings: vi.fn(),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ isAuthenticated: true }),
}))
vi.mock('@/services/http/client', () => ({
  apiGet: vi.fn(async (url) =>
    url.includes('get_account_choices')
      ? { options: [] }
      : {
          choices: {
            default_currency: [
              ['USD', 'Dollar'],
              ['EUR', 'Euro'],
            ],
          },
        }
  ),
}))
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
it('keeps the dialog open and tuple committed until settings refresh succeeds; displays actual failure', async () => {
  let reject
  const canonical = {
    accountSelection: { type: 'all', id: null },
    effectiveCurrentDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  }
  configurePortfolioContextBackend({
    read: vi.fn(async () => canonical),
    updateAccount: vi.fn(),
    updateSettings: () =>
      new Promise((_r, no) => {
        reject = no
      }),
  })
  const store = usePortfolioContextStore()
  await store.reconcileContext()
  const slot = { template: '<div><slot /></div>' }
  const wrapper = mount(SettingsDialog, {
    global: {
      stubs: {
        VBtn: { template: '<button><slot /></button>' },
        VIcon: true,
        VDialog: slot,
        VCard: slot,
        VCardTitle: slot,
        VCardText: slot,
        VCardActions: slot,
        VSpacer: true,
        VForm: slot,
        VSelect: true,
        VTextField: true,
        VAlert: slot,
      },
    },
  })
  await wrapper.vm.openDialog()
  await flushPromises()
  Object.assign(wrapper.vm.formData, {
    default_currency: 'EUR',
    digits: 4,
    table_date: '2025-12-31',
  })
  const saving = wrapper.vm.saveSettings()
  await flushPromises()
  expect(wrapper.vm.dialog).toBe(true)
  expect(store.committed).toMatchObject({
    currency: 'USD',
    digits: 2,
    effectiveCurrentDate: '2026-09-08',
  })
  reject(new Error('Refresh unavailable'))
  await saving
  await flushPromises()
  expect(wrapper.vm.dialog).toBe(true)
  expect(wrapper.text()).toContain('Refresh unavailable')
  wrapper.unmount()
})
it('closes only after the confirmed date/currency/digits tuple is committed', async () => {
  let resolve
  const canonical = {
    accountSelection: { type: 'all', id: null },
    effectiveCurrentDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  }
  configurePortfolioContextBackend({
    read: vi.fn(async () => canonical),
    updateAccount: vi.fn(),
    updateSettings: (settings) =>
      new Promise((done) => {
        resolve = () => {
          Object.assign(canonical, settings)
          done()
        }
      }),
  })
  const store = usePortfolioContextStore()
  await store.reconcileContext()
  const wrapper = mount(SettingsDialog, {
    shallow: true,
    global: {
      stubs: {
        VBtn: true,
        VIcon: true,
        VDialog: true,
        VCard: true,
        VCardTitle: true,
        VCardText: true,
        VCardActions: true,
        VSpacer: true,
        VForm: true,
        VSelect: true,
        VTextField: true,
        VAlert: true,
      },
    },
  })
  wrapper.vm.openDialog()
  Object.assign(wrapper.vm.formData, {
    default_currency: 'EUR',
    digits: 4,
    table_date: '2025-12-31',
  })
  const pending = wrapper.vm.saveSettings()
  await flushPromises()
  expect(wrapper.vm.dialog).toBe(true)
  resolve()
  await pending
  expect(store.committed).toMatchObject({
    currency: 'EUR',
    digits: 4,
    effectiveCurrentDate: '2025-12-31',
  })
  expect(wrapper.vm.dialog).toBe(false)
  wrapper.unmount()
})
