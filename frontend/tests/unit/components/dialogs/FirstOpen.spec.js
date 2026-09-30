import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import AssetTransferDialog from '@/components/dialogs/AssetTransferDialog.vue'
import UpdateAccountPerformanceDialog from '@/components/dialogs/UpdateAccountPerformanceDialog.vue'
import MergerDialog from '@/components/dialogs/MergerDialog.vue'
import * as api from '@/services/api'

vi.mock('@/services/api', () => ({
  getTransactionFormStructure: vi.fn(async () => ({ fields: [] })),
  transferAsset: vi.fn(), getSecurityPosition: vi.fn(),
  getSecurities: vi.fn(async () => []), createMerger: vi.fn(),
  getAccountPerformanceFormData: vi.fn(async () => ({ account_choices: [], currency_choices: {}, is_restricted_choices: {} })),
}))
vi.mock('@/config/axiosConfig', () => ({ default: {} }))
vi.mock('@/composables/useErrorHandler', () => ({ useErrorHandler: () => ({ handleApiError: vi.fn() }) }))

describe('forms mounted on first open', () => {
  beforeEach(() => vi.clearAllMocks())
  it.each([
    [AssetTransferDialog, 'getTransactionFormStructure'],
    [UpdateAccountPerformanceDialog, 'getAccountPerformanceFormData'],
    [MergerDialog, 'getSecurities'],
  ])('loads choices when initially open', async (component, method) => {
    const wrapper = shallowMount(component, { props: { modelValue: true }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(api[method]).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})
