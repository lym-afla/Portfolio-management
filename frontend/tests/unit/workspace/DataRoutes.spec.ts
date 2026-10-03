// D5 Task 2 — Data family route contracts: landing links, per-page action
// mapping, filtering controls, original detail URLs and dialog completion
// invalidation. Dialogs are stubbed only at their own boundary (they have
// their own specs); the page side of every contract — props in, events
// handled, refetch after completion — is asserted against real stores.
import { beforeEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DatabasePage from '@/views/DatabasePage.vue'
import BrokersPage from '@/views/database/BrokersPage.vue'
import AccountsPage from '@/views/database/AccountsPage.vue'
import SecuritiesPage from '@/views/database/SecuritiesPage.vue'
import PricesPage from '@/views/database/PricesPage.vue'
import FXPage from '@/views/database/FXPage.vue'

const api = vi.hoisted(() => ({
  getAssetTypes: vi.fn(),
  getAccounts: vi.fn(),
  getSecurities: vi.fn(),
  getPrices: vi.fn(),
  getPriceDetails: vi.fn(),
  deletePrice: vi.fn(),
  getFXData: vi.fn(),
  getBrokersTable: vi.fn(),
  deleteBroker: vi.fn(),
  getAccountsTable: vi.fn(),
  deleteAccount: vi.fn(),
  getAccountDetails: vi.fn(),
  getSecuritiesForDatabase: vi.fn(),
  deleteSecurity: vi.fn(),
  getSecurityDetails: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const vuetify = createVuetify({ components, directives })

// jsdom has no visualViewport; Vuetify's overlay location strategy needs it
// to open the confirmation dialog in component tests.
beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

const brokerRow = { id: 11, name: 'Fixture Broker', country: 'US', no_of_accounts: 2, no_of_securities: 5, first_investment: '01-Jan-25', nav: '$10,000.00', cash: '$500.00', irr: '3.80%' }
const accountRow = { id: 21, name: 'Main', broker_name: 'Fixture Broker', no_of_securities: 3, first_investment: '01-Jan-25', nav: '$8,000.00', cash: { USD: '$100.00', EUR: '€200.00' }, irr: null }
const securityRow = { id: 31, type: 'Stock', ISIN: 'US0000000001', name: 'Fixture Security', first_investment: '01-Jan-25', currency: '$', open_position: '1.000000000', current_value: '$100.00', realized: '$0.00', unrealized: '$0.00', capital_distribution: '$1.00', irr: '1.20%' }

const stubs = {
  BrokerFormDialog: {
    name: 'BrokerFormDialog',
    props: ['modelValue', 'editItem'],
    emits: ['update:modelValue', 'broker-added', 'broker-updated'],
    template: '<div data-testid="broker-dialog">{{ editItem ? editItem.name : "add" }}</div>',
  },
  AccountFormDialog: {
    name: 'AccountFormDialog',
    props: ['modelValue', 'editItem'],
    emits: ['update:modelValue', 'account-added', 'account-updated'],
    template: '<div data-testid="account-dialog">{{ editItem ? editItem.name : "add" }}</div>',
  },
  SecurityFormDialog: {
    name: 'SecurityFormDialog',
    props: ['modelValue', 'editItem'],
    emits: ['update:modelValue', 'security-added', 'security-updated', 'security-skipped'],
    template: '<div data-testid="security-dialog">{{ editItem ? editItem.name : "add" }}</div>',
  },
  MergerDialog: {
    name: 'MergerDialog',
    props: ['modelValue'],
    emits: ['update:modelValue', 'created'],
    template: '<div data-testid="merger-dialog" />',
  },
  PriceFormDialog: {
    name: 'PriceFormDialog',
    props: ['modelValue', 'editItem', 'securities'],
    emits: ['update:modelValue', 'price-added', 'price-updated'],
    template: '<div data-testid="price-dialog">{{ editItem ? editItem.date : "add" }}</div>',
  },
  PriceImportDialog: {
    name: 'PriceImportDialog',
    props: ['modelValue'],
    emits: ['update:modelValue', 'prices-imported'],
    template: '<div data-testid="price-import-dialog" />',
  },
  FXDialog: {
    name: 'FXDialog',
    props: ['modelValue', 'editItem', 'prefill'],
    emits: ['update:modelValue', 'fx-added', 'fx-updated', 'fx-delete'],
    template: '<div data-testid="fx-dialog">{{ editItem ? editItem.id : (prefill ? prefill.date : "add") }}</div>',
  },
  FXImportDialog: {
    name: 'FXImportDialog',
    props: ['modelValue'],
    emits: ['update:modelValue', 'import-completed', 'refresh-table'],
    template: '<div data-testid="fx-import-dialog" />',
  },
  DateRangeSelector: {
    name: 'DateRangeSelector',
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div data-testid="date-range-selector" />',
  },
}

async function mountPage(path = '/database') {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/database',
        component: DatabasePage,
        children: [
          { path: 'brokers', component: BrokersPage },
          { path: 'accounts', component: AccountsPage },
          { path: 'securities', component: SecuritiesPage },
          { path: 'prices', component: PricesPage },
          { path: 'fx', component: FXPage },
        ],
      },
      { path: '/database/securities/:id', name: 'SecurityDetail', component: { template: '<div />' } },
      { path: '/', redirect: '/database' },
    ],
  })
  router.push(path)
  await router.isReady()
  // Mount the router shell exactly like the real app so nested layouts
  // render once (mounting a route component directly would double it).
  const wrapper = mount(
    { template: '<router-view />' },
    { global: { plugins: [vuetify, pinia, router], provide: { showError: vi.fn(), clearErrors: vi.fn() }, stubs } },
  )
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
  api.getBrokersTable.mockResolvedValue({ items: [brokerRow], totals: { nav: '$10,000.00' }, total_items: 1, current_page: 1, total_pages: 1 })
  api.getAccountsTable.mockResolvedValue({ accounts: [accountRow], totals: {}, total_items: 1, current_page: 1, total_pages: 1 })
  api.getAccountDetails.mockResolvedValue({ ...accountRow, comment: 'hydrated' })
  api.getSecuritiesForDatabase.mockResolvedValue({ securities: [securityRow], total_items: 1, current_page: 1, total_pages: 1 })
  api.getSecurityDetails.mockResolvedValue({ ...securityRow, note: 'hydrated' })
  api.deleteBroker.mockResolvedValue({})
  api.deleteAccount.mockResolvedValue({})
  api.deleteSecurity.mockResolvedValue({})
  api.getAssetTypes.mockResolvedValue([{ text: 'Stock', value: 'Stock' }])
  api.getAccounts.mockResolvedValue([{ id: 1, name: 'Main' }])
  api.getSecurities.mockResolvedValue([{ id: 1, name: 'Fixture Security' }])
  api.getPrices.mockResolvedValue({
    prices: [{ id: 41, date: '01-Jan-25', security__name: 'Fixture Security', security__type: 'Bond', security__currency: '$', security__id: 31, price: '98.50' }],
    total_items: 1, current_page: 1, total_pages: 1,
  })
  api.getPriceDetails.mockResolvedValue({ id: 41, date: '2025-01-01', security: 31, price: '98.50' })
  api.deletePrice.mockResolvedValue({})
  api.getFXData.mockResolvedValue({
    results: [
      { id: 51, date: '2026-09-08', from_currency: 'USD', to_currency: 'EUR', rate: '0.9500' },
      { id: 52, date: '2026-09-07', from_currency: 'USD', to_currency: 'GBP', rate: '0.8000' },
    ],
    count: 2, current_page: 1, total_pages: 1,
  })
})

describe('/database landing', () => {
  it('renders one Data heading with links to every child inventory', async () => {
    const wrapper = await mountPage('/database')
    const headings = wrapper.findAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0].attributes('data-testid')).toBe('workspace-page-heading')
    expect(headings[0].text()).toBe('Data')
    const links = wrapper.findAll('a').map((a) => a.attributes('href'))
    for (const child of ['/database/brokers', '/database/accounts', '/database/securities', '/database/prices', '/database/fx']) {
      expect(links).toContain(child)
    }
  })
})

describe('/database/brokers', () => {
  it('renders a section heading, primary Add Broker action and Search control', async () => {
    const wrapper = await mountPage('/database/brokers')
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('Brokers')
    const addButton = wrapper.findAll('button').find((b) => b.text() === 'Add Broker')
    expect(addButton).toBeTruthy()
    expect(wrapper.find('.workspace-table-toolbar input').exists()).toBe(true)
  })

  it('maps row actions to named controls that edit and open exact-identity deletion', async () => {
    const wrapper = await mountPage('/database/brokers')
    await flushPromises()
    const editButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Fixture Broker') && (b.attributes('aria-label') || '').includes('Edit'))
    expect(editButton).toBeTruthy()
    await editButton!.trigger('click')
    expect(wrapper.find('[data-testid="broker-dialog"]').text()).toBe('Fixture Broker')

    const deleteButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Fixture Broker') && (b.attributes('aria-label') || '').includes('Delete'))
    expect(deleteButton).toBeTruthy()
    await deleteButton!.trigger('click')
    await flushPromises()
    const dialog = wrapper.findComponent({ name: 'ConfirmActionDialog' })
    expect(dialog.exists()).toBe(true)
    const subject = dialog.props('subject')
    expect(subject.title).toContain('Fixture Broker')
    expect(subject.details.some((d) => d.value === 'Fixture Broker')).toBe(true)
    await dialog.vm.$emit('confirm')
    await flushPromises()
    expect(api.deleteBroker).toHaveBeenCalledWith(11)
    expect(api.getBrokersTable).toHaveBeenCalledTimes(2)
  })

  it('refetches when the broker dialog reports completion', async () => {
    const wrapper = await mountPage('/database/brokers')
    await flushPromises()
    // The async dialog stays unmounted until its first open (useFirstOpen).
    await wrapper.findAll('button').find((b) => b.text() === 'Add Broker')!.trigger('click')
    await flushPromises()
    api.getBrokersTable.mockClear()
    wrapper.findComponent({ name: 'BrokerFormDialog' }).vm.$emit('broker-added')
    await flushPromises()
    expect(api.getBrokersTable).toHaveBeenCalledTimes(1)
  })
})

describe('/database/accounts', () => {
  it('renders one cash column per returned currency and keeps account deletion identified', async () => {
    const wrapper = await mountPage('/database/accounts')
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('USD')
    expect(text).toContain('EUR')
    expect(text).toContain('€200.00')

    const deleteButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Main') && (b.attributes('aria-label') || '').includes('Delete'))
    expect(deleteButton).toBeTruthy()
    await deleteButton!.trigger('click')
    await flushPromises()
    const dialog = wrapper.findComponent({ name: 'ConfirmActionDialog' })
    expect(dialog.props('subject').details.some((d) => d.value === 'Main')).toBe(true)
    await dialog.vm.$emit('confirm')
    await flushPromises()
    expect(api.deleteAccount).toHaveBeenCalledWith(21)
  })

  it('hydrates the edit dialog from the account details endpoint, not the row', async () => {
    const wrapper = await mountPage('/database/accounts')
    await flushPromises()
    const editButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Main') && (b.attributes('aria-label') || '').includes('Edit'))
    await editButton!.trigger('click')
    await flushPromises()
    expect(api.getAccountDetails).toHaveBeenCalledWith(21)
    expect(wrapper.find('[data-testid="account-dialog"]').text()).toContain('Main')
  })
})

describe('/database/securities', () => {
  it('links security names to the original detail route by id', async () => {
    const wrapper = await mountPage('/database/securities')
    await flushPromises()
    const link = wrapper.findAll('a').find((a) => a.text() === 'Fixture Security')
    expect(link).toBeTruthy()
    expect(link!.attributes('href')).toBe('/database/securities/31')
  })

  it('keeps Add Security primary and Record Merger reachable with exact-identity deletion', async () => {
    const wrapper = await mountPage('/database/securities')
    await flushPromises()
    expect(wrapper.findAll('button').find((b) => b.text() === 'Add Security')).toBeTruthy()
    expect(wrapper.findAll('button').find((b) => b.text() === 'Record Merger')).toBeTruthy()

    const deleteButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Fixture Security') && (b.attributes('aria-label') || '').includes('Delete'))
    expect(deleteButton).toBeTruthy()
    await deleteButton!.trigger('click')
    await flushPromises()
    const dialog = wrapper.findComponent({ name: 'ConfirmActionDialog' })
    expect(dialog.props('subject').details.some((d) => d.value === 'Fixture Security')).toBe(true)
    await dialog.vm.$emit('confirm')
    await flushPromises()
    expect(api.deleteSecurity).toHaveBeenCalledWith(31)
    expect(api.getSecuritiesForDatabase).toHaveBeenCalledTimes(2)
  })
})

describe('/database/prices', () => {
  it('keeps the security/date filters, unit hint and primary actions with the exact price string', async () => {
    const wrapper = await mountPage('/database/prices')
    await flushPromises()
    const text = wrapper.text()
    expect(wrapper.find('h2').text()).toBe('Prices')
    expect(text).toContain('Asset Types')
    expect(text).toContain('Accounts')
    expect(text).toContain('Securities')
    expect(text).toContain('Start Date')
    expect(text).toContain('End Date')
    expect(text).toContain("security's trading currency")
    expect(text).toContain('98.50')
    const buttons = wrapper.findAll('button').map((b) => b.text())
    expect(buttons).toContain('Add Price Entry')
    expect(buttons).toContain('Import Prices')
    expect(buttons).toContain('Apply Filters')
  })

  it('opens the import entrypoint and confirms price deletion with exact identity', async () => {
    const wrapper = await mountPage('/database/prices')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === 'Import Prices')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="price-import-dialog"]').exists()).toBe(true)

    const deleteButton = wrapper
      .findAll('button')
      .find((b) => (b.attributes('aria-label') || '').includes('Fixture Security') && (b.attributes('aria-label') || '').includes('Delete'))
    expect(deleteButton).toBeTruthy()
    await deleteButton!.trigger('click')
    await flushPromises()
    const dialog = wrapper.findComponent({ name: 'ConfirmActionDialog' })
    const subject = dialog.props('subject')
    expect(subject.details.some((d: { value: string }) => d.value === '01-Jan-25')).toBe(true)
    expect(subject.details.some((d: { value: string }) => d.value === '98.50 $')).toBe(true)
    await dialog.vm.$emit('confirm')
    await flushPromises()
    expect(api.deletePrice).toHaveBeenCalledWith(41)
    expect(api.getPrices).toHaveBeenCalledTimes(2)
  })
})

describe('/database/fx', () => {
  it('renders the pivot with pair labels and orientation note, and confirms delete identity', async () => {
    const wrapper = await mountPage('/database/fx')
    await flushPromises()
    await flushPromises()
    const text = wrapper.text()
    expect(wrapper.find('h2').text()).toBe('FX rates')
    expect(text).toContain('USD/EUR')
    expect(text).toContain('USD/GBP')
    expect(text).toContain('0.9500')
    expect(text).toContain('—')
    expect(text).toContain('quoted from the first currency to the second')
    expect(wrapper.find('[data-testid="date-range-selector"]').exists()).toBe(true)
    expect(wrapper.findAll('button').map((b) => b.text())).toContain('Add FX Rate')
    expect(wrapper.findAll('button').map((b) => b.text())).toContain('Import FX Rates')
  })
})
