import { describe, expect, it } from 'vitest'

import {
  decodeAccountsTable,
  decodeBrokersTable,
  decodePricesTable,
  decodeSecuritiesTable,
} from '@/services/api/database'
import { resolveFixture } from '../../../tests/browser/fixtures.mjs'

describe('browser database fixtures', () => {
  it('provides representative rows accepted by the production table decoders', () => {
    const accounts = resolveFixture('POST', '/database/api/accounts/list_accounts/')
    const brokers = resolveFixture('POST', '/database/api/brokers/list_brokers/')
    const prices = resolveFixture('POST', '/database/api/get-prices-table/')
    const securities = resolveFixture('POST', '/database/api/get-securities-for-database/')

    expect(decodeAccountsTable(accounts.body).accounts[0].name).toBe('Main')
    expect(decodeBrokersTable(brokers.body).items[0].name).toBe('Fixture Broker')
    expect(decodePricesTable(prices.body).prices[0].security__name).toBe('Fixture Security')
    expect(decodeSecuritiesTable(securities.body).securities[0].name).toBe('Fixture Security')
  })
})
