const profile = {
  id: 1,
  username: 'fixture-user',
  email: 'fixture@example.invalid',
  first_name: 'Fixture',
  last_name: 'User',
  digits: 2,
  default_currency: 'USD',
  selected_account_type: 'all',
  selected_account_id: null,
}

const fixtures = new Map([
  ['GET /users/api/profile/', profile],
  ['GET /users/api/get_account_choices/', { options: [] }],
  [
    'GET /users/api/dashboard_settings/',
    {
      settings: { default_currency: 'USD', digits: 2, table_date: '2026-09-08' },
      choices: { default_currency: [['USD', 'US Dollar']] },
    },
  ],
  ['GET /api/effective-current-date/', { effective_current_date: '2026-09-08' }],
  ['GET /api/get-year-options/', { table_years: [2026] }],
  [
    'GET /users/api/user_settings/',
    {
      default_currency: 'USD',
      use_default_currency_where_relevant: true,
      chart_frequency: 'M',
      chart_timeline: 'YTD',
      NAV_barchart_default_breakdown: 'none',
      digits: 2,
      selected_account_type: 'all',
      selected_account_id: null,
    },
  ],
  [
    'GET /users/api/user_settings_choices/',
    {
      currency_choices: [['USD', 'US Dollar']],
      frequency_choices: [['M', 'Monthly']],
      timeline_choices: [['YTD', 'Year to date']],
      nav_breakdown_choices: [['none', 'No breakdown']],
      account_choices: [],
    },
  ],
  ['GET /users/api/account-groups/', []],
  [
    'GET /users/api/broker_tokens/',
    { tinkoff_tokens: [], ib_tokens: [], bybit_tokens: [], okx_tokens: [] },
  ],
  [
    'GET /dashboard/api/get-summary/',
    {
      'Current NAV': '$100.00',
      Invested: '$100.00',
      'Cash-out': '$0.00',
      total_return: '0.00%',
      irr: '0.00%',
    },
  ],
  [
    'GET /dashboard/api/get-breakdown/',
    { assetType: {}, assetClass: {}, currency: {}, totalNAV: '$100.00' },
  ],
  [
    'GET /dashboard/api/get-summary-over-time/',
    { lines: [], years: [], currentYear: 2026 },
  ],
  ['GET /dashboard/api/get-nav-chart-data/', { labels: [], datasets: [] }],
  [
    'POST /open_positions/api/get_open_positions_table/',
    {
      portfolio_open: [],
      portfolio_open_totals: {},
      cash_balances: {},
      total_items: 0,
      current_page: 1,
      total_pages: 1,
    },
  ],
  [
    'POST /closed_positions/api/get_closed_positions_table/',
    { portfolio_closed: [], portfolio_closed_totals: {}, cash_balances: null, total_items: 0, current_page: 1, total_pages: 1 },
  ],
  [
    'POST /transactions/api/get_transactions_table/',
    { transactions: [], total_items: 0, current_page: 1, total_pages: 1, currencies: ['USD'] },
  ],
  ['GET /transactions/api/form_structure/', { fields: [] }],
  ['GET /transactions/api/fx/form_structure/', { fields: [] }],
  ['GET /ws/transactions/', null],
  ['POST /database/api/accounts/list_accounts/', {
    accounts: [{ id: 1, name: 'Main', broker_name: 'Fixture Broker', no_of_securities: 1, first_investment: '01-Jan-25', nav: '$100.00', cash: { USD: '$50.00' }, irr: null }],
    totals: {}, total_items: 1, current_page: 1, total_pages: 1,
  }],
  ['POST /database/api/brokers/list_brokers/', {
    items: [{ id: 1, name: 'Fixture Broker', country: 'US', no_of_accounts: 1, no_of_securities: 1, first_investment: '01-Jan-25', nav: '$100.00', cash: '$50.00', irr: null }],
    totals: {}, total_items: 1, current_page: 1, total_pages: 1,
  }],
  ['GET /database/api/get-asset-types/', []],
  ['GET /database/api/get-securities/', []],
  ['GET /database/api/accounts/', []],
  ['GET /database/api/brokers/', []],
  ['GET /database/api/brokers/form_structure/', { fields: [] }],
  ['GET /database/api/accounts/form_structure/', { fields: [] }],
  ['GET /database/api/security-form-structure/', { fields: [] }],
  [
    'GET /database/api/price-import/',
    { securities: [], accounts: [], frequency_choices: [] },
  ],
  ['GET /database/api/fx/form_structure/', { fields: [] }],
  ['GET /database/api/fx/import_stats/', { total_records: 0, latest_date: null }],
  ['POST /database/api/get-prices-table/', {
    prices: [{ id: 1, date: '01-Jan-25', security__name: 'Fixture Security', security__type: 'Stock', security__currency: '$', security__id: 1, price: '100.00' }],
    total_items: 1, current_page: 1, total_pages: 1,
  }],
  [
    'POST /database/api/get-securities-for-database/',
    {
      securities: [{ id: 1, type: 'Stock', ISIN: 'US0000000001', name: 'Fixture Security', first_investment: '01-Jan-25', currency: '$', open_position: '1.000000000', current_value: '$100.00', realized: '$0.00', unrealized: '$0.00', capital_distribution: '$0.00', irr: null }],
      total_items: 1, current_page: 1, total_pages: 1,
    },
  ],
  ['POST /database/api/fx/list_fx/', { results: [], count: 0, current_page: 1, total_pages: 1 }],
  [
    'GET /database/api/securities/1/',
    {
      id: 1,
      instrument_type: 'Stock',
      ISIN: 'US0000000001',
      name: 'Fixture Security',
      currency: 'USD',
      first_investment: '08-Sep-26',
      open_position: '1.000000000',
      current_value: '$100.00',
      realized: '$0.00',
      unrealized: '$0.00',
      capital_distribution: '$100.00',
      irr: '0.00%',
    },
  ],
  ['GET /database/api/securities/1/price-history/', []],
  ['GET /database/api/securities/1/position-history/', []],
  [
    'GET /database/api/securities/1/transactions/',
    { transactions: [], total_items: 0 },
  ],
  [
    'GET /summary/api/summary_data/',
    {
      public_markets_context: { lines: [], subtotal: null },
      restricted_investments_context: { lines: [], subtotal: null },
      total_context: { line: {}, years: [] },
    },
  ],
  [
    'GET /summary/api/portfolio_breakdown/',
    { consolidated_context: [], public_markets_context: [], restricted_context: [] },
  ],
])

export function resolveFixture(method, pathname) {
  const key = `${method.toUpperCase()} ${pathname}`
  if (!fixtures.has(key)) {
    throw new Error(`Unmatched fixture request: ${key}`)
  }

  return { status: 200, body: structuredClone(fixtures.get(key)) }
}
