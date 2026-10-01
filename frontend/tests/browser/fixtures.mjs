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
  // Dense synthetic dashboard fixtures for the D3 visual pilot: committed
  // provenance flows through the app shell; summary values include zero,
  // negative (Unicode minus) and unavailable (null) display strings that must
  // survive display-only rendering untouched.
  [
    'GET /dashboard/api/get-summary/',
    {
      'Current NAV': '$100.00',
      Invested: '$90.00',
      'Cash-out': '($25.00)',
      total_return: '−2.40%',
      irr: null,
    },
  ],
  [
    'GET /dashboard/api/get-breakdown/',
    {
      assetType: {
        data: { Stocks: '$62.00', Bonds: '$18.00', 'Cash-like': '$12.00', Crypto: '$8.00' },
        percentage: { Stocks: '62%', Bonds: '18%', 'Cash-like': '12%', Crypto: '8%' },
      },
      assetClass: {
        data: { Equity: '$70.00', 'Fixed Income': '$18.00', 'Cash & Equivalents': '$12.00' },
        percentage: { Equity: '70%', 'Fixed Income': '18%', 'Cash & Equivalents': '12%' },
      },
      currency: {
        data: { USD: '$68.00', EUR: '$22.00', GBP: '$10.00' },
        percentage: { USD: '68%', EUR: '22%', GBP: '10%' },
      },
      totalNAV: '$100.00',
    },
  ],
  [
    'GET /dashboard/api/get-summary-over-time/',
    {
      lines: [
        { name: 'BoP NAV', data: { 2023: '$80.00', 2024: '$85.00', 2025: '$88.00', YTD: '$90.00', 'All-time': '$0.00' } },
        { name: 'Invested', data: { 2023: '$70.00', 2024: '$75.00', 2025: '$80.00', YTD: '$90.00', 'All-time': '$90.00' } },
        { name: 'Cash out', data: { 2023: '($5.00)', 2024: '($10.00)', 2025: '($15.00)', YTD: '($25.00)', 'All-time': '($25.00)' } },
        { name: 'Price change', data: { 2023: '$3.00', 2024: '$4.00', 2025: '$5.00', YTD: '$6.00', 'All-time': '$18.00' } },
        { name: 'Capital distribution', data: { 2023: '$2.00', 2024: '$2.00', 2025: '$2.00', YTD: '$1.00', 'All-time': '$7.00' } },
        { name: 'Commission', data: { 2023: '($1.00)', 2024: '($1.00)', 2025: '($1.00)', YTD: '($0.50)', 'All-time': '($3.50)' } },
        { name: 'Tax', data: { 2023: '$0.00', 2024: '$0.00', 2025: '$0.00', YTD: '$0.00', 'All-time': '$0.00' } },
        { name: 'FX', data: { 2023: '$1.00', 2024: '($1.00)', 2025: '$2.00', YTD: '$1.00', 'All-time': '$3.00' } },
        { name: 'EoP NAV', data: { 2023: '$85.00', 2024: '$88.00', 2025: '$90.00', YTD: '$100.00', 'All-time': '$100.00' } },
        { name: 'TSR', data: { 2023: '6.25%', 2024: '3.53%', 2025: '2.27%', YTD: '11.11%', 'All-time': '25.00%' } },
      ],
      years: [2023, 2024, 2025],
      currentYear: 2026,
    },
  ],
  // NAV series mirrors the legacy chart contract: NAV bars on the primary
  // axis plus both since-inception and rolling IRR lines on the secondary
  // axis, with unavailable early values as null.
  [
    'GET /dashboard/api/get-nav-chart-data/',
    {
      currency: 'USDk',
      labels: ['Jan-26', 'Feb-26', 'Mar-26', 'Apr-26', 'May-26', 'Jun-26', 'Jul-26', 'Aug-26', 'Sep-26'],
      datasets: [
        {
          label: 'NAV',
          type: 'bar',
          yAxisID: 'y',
          data: [80.2, 81.5, 79.8, 83.2, 84.9, 83.1, 86.4, 87.8, 89.2],
          backgroundColor: '#1976d2',
          borderColor: '#1976d2',
          datalabels: { display: 'true' },
        },
        {
          label: 'IRR (RHS)',
          type: 'line',
          yAxisID: 'y1',
          data: [null, 1.2, 1.1, 2.4, 3.1, 2.8, 3.9, 4.2, 4.6],
          backgroundColor: '#ef5350',
          borderColor: '#ef5350',
          fill: false,
          datalabels: { display: 'true' },
        },
        {
          label: 'Rolling IRR (RHS)',
          type: 'line',
          yAxisID: 'y1',
          data: [null, null, 1.8, 2.1, 2.6, 2.4, 3.0, 3.3, 3.5],
          backgroundColor: '#66bb6a',
          borderColor: '#66bb6a',
          fill: false,
          datalabels: { display: 'true' },
        },
      ],
    },
  ],
  // Dense synthetic Open Positions: long security names, two currencies,
  // zero/negative/unavailable display values and every leaf column populated
  // so the grouped headers, totals and sticky identity can be reviewed.
  [
    'POST /open_positions/api/get_open_positions_table/',
    {
      portfolio_open: [
        {
          id: 1, type: 'Stock', name: 'International Business Machines Corporation Consolidated Class A', currency: 'USD',
          current_position: '1,000.000000000', investment_date: '14-Mar-23', entry_price: '$120.50', entry_value: '$120,500.00',
          current_price: '$145.25', current_value: '$145,250.00', share_of_portfolio: '31.5%',
          price_change_percentage: '20.54%', realized_gl: '$0.00', unrealized_gl: '$24,750.00',
          capital_distribution: '$1,200.00', capital_distribution_percentage: '1.00%',
          commission: '($150.00)', commission_percentage: '0.12%',
          total_return_amount: '$25,800.00', total_return_percentage: '21.41%', irr: '12.30%',
        },
        {
          id: 2, type: 'Stock', name: 'Koninklijke Philips N.V. New York Registry Shares', currency: 'EUR',
          current_position: '2,500.000000000', investment_date: '02-Jun-23', entry_price: '€18.40', entry_value: '€46,000.00',
          current_price: '€21.10', current_value: '€52,750.00', share_of_portfolio: '11.4%',
          price_change_percentage: '14.67%', realized_gl: '$0.00', unrealized_gl: '€6,750.00',
          capital_distribution: '€500.00', capital_distribution_percentage: '1.09%',
          commission: '(€60.00)', commission_percentage: '0.13%',
          total_return_amount: '€7,190.00', total_return_percentage: '15.63%', irr: '8.90%',
        },
        {
          id: 3, type: 'Bond', name: 'United States Treasury Note 2.375% 15-Aug-2031', currency: 'USD',
          current_position: '50.000000000', investment_date: '21-Nov-23', entry_price: '98.50', entry_value: '$49,250.00',
          current_price: '101.25', current_value: '$50,625.00', share_of_portfolio: '11.0%',
          price_change_percentage: '2.79%', realized_gl: '$0.00', unrealized_gl: '$1,375.00',
          capital_distribution: '$2,375.00', capital_distribution_percentage: '4.82%',
          commission: '($25.00)', commission_percentage: '0.05%',
          total_return_amount: '$3,725.00', total_return_percentage: '7.56%', irr: '4.65%',
        },
        {
          id: 4, type: 'Crypto', name: 'Bitcoin', currency: 'USD',
          current_position: '0.750000000', investment_date: '09-Jan-24', entry_price: '$42,000.00', entry_value: '$31,500.00',
          current_price: '$38,400.00', current_value: '$28,800.00', share_of_portfolio: '6.2%',
          price_change_percentage: '−8.57%', realized_gl: '$0.00', unrealized_gl: '($2,700.00)',
          capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
          commission: '($40.00)', commission_percentage: '0.13%',
          total_return_amount: '($2,740.00)', total_return_percentage: '−8.70%', irr: '−15.20%',
        },
        {
          id: 5, type: 'ETF', name: 'Vanguard FTSE Developed Markets Index Fund ETF Shares', currency: 'GBP',
          current_position: '600.000000000', investment_date: '17-Feb-24', entry_price: '£26.80', entry_value: '£16,080.00',
          current_price: '£26.80', current_value: '£16,080.00', share_of_portfolio: '3.5%',
          price_change_percentage: '0.00%', realized_gl: '$0.00', unrealized_gl: '£0.00',
          capital_distribution: '£180.00', capital_distribution_percentage: '1.12%',
          commission: '(£12.00)', commission_percentage: '0.07%',
          total_return_amount: '£168.00', total_return_percentage: '1.04%', irr: '1.90%',
        },
        {
          id: 6, type: 'Stock', name: 'Samsung Electronics Co., Ltd. Common Shares GDR', currency: 'USD',
          current_position: '0.000000000', investment_date: '05-May-24', entry_price: '$1,350.00', entry_value: '$40,500.00',
          current_price: 'N/R', current_value: '$0.00', share_of_portfolio: '0.0%',
          price_change_percentage: 'N/R', realized_gl: '$0.00', unrealized_gl: '($40,500.00)',
          capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
          commission: '($30.00)', commission_percentage: '0.07%',
          total_return_amount: '($40,530.00)', total_return_percentage: '−100.07%', irr: '−78.40%',
        },
        {
          id: 7, type: 'Fund', name: 'BlackRock Global Funds - World Healthscience Fund D2', currency: 'EUR',
          current_position: '1,200.000000000', investment_date: '30-Aug-24', entry_price: '€24.15', entry_value: '€28,980.00',
          current_price: '€27.30', current_value: '€32,760.00', share_of_portfolio: '7.1%',
          price_change_percentage: '13.04%', realized_gl: '$0.00', unrealized_gl: '€3,780.00',
          capital_distribution: '€0.00', capital_distribution_percentage: '0.00%',
          commission: '(€35.00)', commission_percentage: '0.12%',
          total_return_amount: '€3,745.00', total_return_percentage: '12.92%', irr: '9.80%',
        },
        {
          id: 8, type: 'Stock', name: 'Novo Nordisk A/S B Share Copenhagen', currency: 'USD',
          current_position: '150.000000000', investment_date: '12-Dec-24', entry_price: '$102.40', entry_value: '$15,360.00',
          current_price: '$74.90', current_value: '$11,235.00', share_of_portfolio: '2.4%',
          price_change_percentage: '−26.86%', realized_gl: '$0.00', unrealized_gl: '($4,125.00)',
          capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
          commission: '($18.00)', commission_percentage: '0.12%',
          total_return_amount: '($4,143.00)', total_return_percentage: '−27.00%', irr: 'N/R',
        },
      ],
      portfolio_open_totals: {
        type: 'Total for assets',
        current_position: '',
        investment_date: '',
        entry_price: '',
        entry_value: '$331,670.00',
        current_price: '',
        current_value: '$337,500.00',
        share_of_portfolio: '100%',
        price_change_percentage: '',
        realized_gl: '$0.00',
        unrealized_gl: '$13,855.00',
        capital_distribution: '$4,255.00',
        capital_distribution_percentage: '',
        commission: '($370.00)',
        commission_percentage: '',
        total_return_amount: '$9,740.00',
        total_return_percentage: '2.94%',
        irr: '3.80%',
        cash: '$18,750.00',
        cash_share_of_portfolio: '4.1%',
        total_nav: '$356,250.00',
      },
      cash_balances: { USD: '$12,500.00', EUR: '€5,100.00', GBP: '£1,150.00' },
      total_items: 8,
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
  ['GET /database/api/update-account-performance/', { account_choices: [], currency_choices: {}, is_restricted_choices: {} }],
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

export function resolveFixture(method, pathname, { longAccount = false } = {}) {
  const key = `${method.toUpperCase()} ${pathname}`
  if (longAccount && key === 'GET /users/api/user_settings/') return { status: 200, body: { ...structuredClone(fixtures.get(key)), selected_account_type: 'account', selected_account_id: 1 } }
  if (longAccount && key === 'GET /users/api/get_account_choices/') {
    const selected = {
      id: 1,
      type: 'account',
      display_name: 'Long synthetic investment account name for narrow viewport wrapping',
    }
    return { status: 200, body: { options: [['Account', selected]], selected } }
  }
  if (!fixtures.has(key)) {
    throw new Error(`Unmatched fixture request: ${key}`)
  }

  return { status: 200, body: structuredClone(fixtures.get(key)) }
}
