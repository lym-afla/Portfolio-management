import { configurePortfolioContextBackend } from '@/services/api/context'
import { configureApiTransport } from '@/services/http/client'
/** Complete synthetic canonical bootstrap for component tests using the real stores. */
export function configureContextFixture(date = '2026-08-18') {
  const values = {
    accountSelection: { type: 'all', id: null },
    effectiveCurrentDate: date,
    currency: 'USD',
    digits: 2,
  }
  configurePortfolioContextBackend({
    read: async () => values,
    updateAccount: async (selection) => {
      values.accountSelection = selection
    },
    updateSettings: async (settings) => {
      Object.assign(values, settings)
    },
  })
  configureApiTransport({
    get: async (url) => ({
      data: url.includes('get_account_choices')
        ? { options: [['All accounts', { type: 'all', id: null }]] }
        : { choices: { default_currency: [['USD', 'Dollar']] } },
    }),
  })
}
