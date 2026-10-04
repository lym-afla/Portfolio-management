import { d4FxFormStructure, d4RegularFormStructure, d4Transactions } from './d4-datasets.mjs'

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
  // axis, with unavailable early values as null. chartV2 carries the exact
  // C1 contract beside it (raw values, plot values /1000, month-end ISO
  // endpoints, both IRR horizons) so the default matrix exercises the C2
  // typed boundary end to end.
  [
    'GET /dashboard/api/get-nav-chart-data/',
    (() => {
      const labels = ['Jan-26', 'Feb-26', 'Mar-26', 'Apr-26', 'May-26', 'Jun-26', 'Jul-26', 'Aug-26', 'Sep-26']
      const endDates = ['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30', '2026-05-31', '2026-06-30', '2026-07-31', '2026-08-31', '2026-09-08']
      const starts = [null, '2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01', '2026-09-01']
      const navPlot = [80.2, 81.5, 79.8, 83.2, 84.9, 83.1, 86.4, 87.8, 89.2]
      const irr = [null, 1.2, 1.1, 2.4, 3.1, 2.8, 3.9, 4.2, 4.6]
      const rolling = [null, null, 1.8, 2.1, 2.6, 2.4, 3.0, 3.3, 3.5]
      const raw = (plot) => String(Math.round(plot * 1000))
      // Synthetic displays mirror the real backend currency_format output:
      // thousands separators, configured precision and signed parentheses —
      // fixtures must stay faithful to the observed wire contract.
      const grouped = (text) => text.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
      const money = (plot) => {
        const whole = Math.round(plot * 1000)
        const sign = whole < 0 ? '(' : ''
        const close = whole < 0 ? ')' : ''
        return `${sign}$${grouped(String(Math.abs(whole)))}.00${close}`
      }
      const ok = (value, plot, display) => ({ value, plotValue: plot, status: 'ok', reason: 'observed', display })
      const unavailable = () => ({ value: null, plotValue: null, status: 'not_available', reason: 'solver_unavailable', display: 'N/A' })
      const irrPoints = (values) => values.map((value) => (value === null ? unavailable() : ok(`0.0${String(value).replace('.', '')}`, `0.0${String(value).replace('.', '')}`, `${value}%`)))
      return {
        currency: 'USDk',
        labels,
        datasets: [
          {
            label: 'NAV',
            type: 'bar',
            yAxisID: 'y',
            data: [...navPlot],
            backgroundColor: '#1976d2',
            borderColor: '#1976d2',
            datalabels: { display: 'true' },
          },
          {
            label: 'IRR (RHS)',
            type: 'line',
            yAxisID: 'y1',
            data: [...irr],
            backgroundColor: '#ef5350',
            borderColor: '#ef5350',
            fill: false,
            datalabels: { display: 'true' },
          },
          {
            label: 'Rolling IRR (RHS)',
            type: 'line',
            yAxisID: 'y1',
            data: [...rolling],
            backgroundColor: '#66bb6a',
            borderColor: '#66bb6a',
            fill: false,
            datalabels: { display: 'true' },
          },
        ],
        chartV2: {
          version: 2,
          kind: 'nav',
          outcome: 'ready',
          partition: 'complete',
          context: {
            accountSelection: { type: 'all', id: null },
            accountIds: [],
            effectiveDate: '2026-09-08',
            currency: 'USD',
            digits: 2,
          },
          periods: endDates.map((endDate, index) => ({
            key: `nav:${endDate}`,
            endDate,
            displayLabel: labels[index],
            interval: { startDate: starts[index], endDate, kind: index === 0 ? 'inception' : 'sample_interval' },
            partialPeriod: endDate === '2026-09-08',
          })),
          series: [
            {
              id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money',
              unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
              points: navPlot.map((plot) => ok(raw(plot), String(plot), money(plot))),
            },
            {
              id: 'metric:irr_inception', label: 'IRR (RHS)', metric: 'irr_inception', role: 'line', axis: 'return',
              unit: { kind: 'ratio', plotDivisor: '1' }, points: irrPoints(irr),
            },
            {
              id: 'metric:irr_interval', label: 'Rolling IRR (RHS)', metric: 'irr_interval', role: 'line', axis: 'return',
              unit: { kind: 'ratio', plotDivisor: '1' }, points: irrPoints(rolling),
            },
          ],
          totals: navPlot.map((plot) => ok(raw(plot), String(plot), money(plot))),
        },
      }
    })(),
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
    { transactions: structuredClone(d4Transactions), total_items: d4Transactions.length, current_page: 1, total_pages: 1, currencies: ['USD', 'EUR'] },
  ],
  ['GET /transactions/api/form_structure/', structuredClone(d4RegularFormStructure)],
  ['GET /transactions/api/fx/form_structure/', structuredClone(d4FxFormStructure)],
  ['GET /transactions/api/5/', { id: 5, account: 1, security: 1, currency: 'USD', date: '2026-09-08', type: 'Buy', quantity: '10', price: '120.50', commission: '-15.00', cash_flow: '-1215.00' }],
  ['GET /transactions/api/fx/5/', { id: 5, account: 1, date: '2026-09-01', from_currency: 'EUR', to_currency: 'USD', commission_currency: 'GBP', from_amount: '-1000.00', to_amount: '1080.00', exchange_rate: '1.08', commission: '-8.00' }],
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
  // Populated FX pivot (backend list_fx shape): a few dates x pairs, one
  // missing cell (GBP on the earlier date) so the em-dash marker renders.
  [
    'POST /database/api/fx/list_fx/',
    {
      results: [
        { id: 101, date: '2026-09-08', from_currency: 'USD', to_currency: 'EUR', rate: '0.9500' },
        { id: 102, date: '2026-09-08', from_currency: 'USD', to_currency: 'GBP', rate: '0.8000' },
        { id: 103, date: '2026-09-05', from_currency: 'USD', to_currency: 'EUR', rate: '0.9480' },
        { id: 104, date: '2026-09-05', from_currency: 'CHF', to_currency: 'GBP', rate: '0.9120' },
      ],
      count: 4, current_page: 1, total_pages: 1,
    },
  ],
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
  // /summary: backend-faithful shape (services/summary.py) — server period
  // order YTD / calendar years descending / All-time; eight metric keys per
  // period; the Sub-total line travels INSIDE each context's lines (there is
  // no separate subtotal key on the wire); TOTAL comes from total_context.
  // Values include comma-grouped, signed, percentage and N/A display strings
  // that must render verbatim.
  [
    'GET /summary/api/summary_data/',
    (() => {
      const periods = ['YTD', '2025', '2024', 'All-time']
      const metrics = (overrides = {}) => {
        const base = {
          'BoP NAV': '$10,000.00',
          'Cash-in/out': '($1,000.00)',
          Return: '$2,500.00',
          FX: '$10.00',
          'TSR percentage': '6.25%',
          'EoP NAV': '$11,500.00',
          Commission: '($25.00)',
          'Fee per AuM (percentage)': '0.05%',
        }
        return Object.fromEntries(
          periods.map((period) => [period, { ...base, ...(overrides[period] || {}) }]),
        )
      }
      return {
        public_markets_context: {
          years: periods,
          lines: [
            { name: 'Fixture Broker — Main', data: metrics({ 2024: { FX: 'N/A' } }) },
            { name: 'Fixture Broker — IRA', data: metrics({ 'All-time': { 'TSR percentage': '8.10%' } }) },
            { name: 'Sub-total', data: metrics() },
          ],
        },
        restricted_investments_context: {
          years: periods,
          lines: [
            { name: 'Fixture Broker — Restricted', data: metrics({ YTD: { 'Fee per AuM (percentage)': 'N/A' } }) },
            { name: 'Sub-total', data: metrics() },
          ],
        },
        total_context: { line: { name: 'TOTAL', data: metrics() }, years: periods },
      }
    })(),
  ],
  [
    'GET /summary/api/portfolio_breakdown/',
    {
      consolidated_context: [
        { name: 'Stocks', cost: '$80,000.00', unrealized: '$9,740.00', unrealized_percent: '12.18%', market_value: '$89,740.00', portfolio_percent: '71.79%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$1,200.00', capital_distribution_percent: '1.50%', commission: '($370.00)', commission_percent: '0.46%', total: '$10,570.00', total_percent: '13.21%' },
        { name: 'Bonds', cost: '$18,000.00', unrealized: '$1,375.00', unrealized_percent: '7.64%', market_value: '$19,375.00', portfolio_percent: '15.50%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$2,375.00', capital_distribution_percent: '13.19%', commission: '($25.00)', commission_percent: '0.14%', total: '$3,725.00', total_percent: '20.69%' },
        { name: 'Cash-like', cost: '$15,000.00', unrealized: '$0.00', unrealized_percent: '0%', market_value: '$15,000.00', portfolio_percent: '12.00%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$0.00', capital_distribution_percent: '0%', commission: '($5.00)', commission_percent: '0.03%', total: '($5.00)', total_percent: '0.03%' },
        { name: 'TOTAL', cost: '$113,000.00', unrealized: '$11,115.00', unrealized_percent: '9.84%', market_value: '$124,115.00', portfolio_percent: '99.29%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$3,575.00', capital_distribution_percent: '3.16%', commission: '($400.00)', commission_percent: '0.35%', total: '$14,290.00', total_percent: '12.64%' },
      ],
      unrestricted_context: [
        { name: 'Stocks', cost: '$60,000.00', unrealized: '$8,000.00', unrealized_percent: '13.33%', market_value: '$68,000.00', portfolio_percent: '54.40%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$900.00', capital_distribution_percent: '1.50%', commission: '($270.00)', commission_percent: '0.45%', total: '$8,630.00', total_percent: '14.38%' },
      ],
      restricted_context: [
        { name: 'Stocks', cost: '$20,000.00', unrealized: '$1,740.00', unrealized_percent: '8.70%', market_value: '$21,740.00', portfolio_percent: '17.39%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$300.00', capital_distribution_percent: '1.50%', commission: '($100.00)', commission_percent: '0.50%', total: '$1,940.00', total_percent: '9.70%' },
      ],
    },
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

// ---- D4 grouped-tables/actions datasets ---------------------------------
// Multi-page positions whose SERVER order is a fixed shuffle that ignores
// the requested sort (the rendered table must display exactly this order),
// plus duplicate-numeric-id transactions with detail delay/failure and a
// first-failing deletion.
export const d4OpenRows = [
  { id: 3, type: 'Bond', name: 'United States Treasury Note 2.375% 15-Aug-2031', currency: 'USD',
    current_position: '50.000000000', investment_date: '21-Nov-23', entry_price: '98.50', entry_value: '$49,250.00',
    current_price: '101.25', current_value: '$50,625.00', share_of_portfolio: '14.1%',
    price_change_percentage: '2.79%', realized_gl: '$0.00', unrealized_gl: '$1,375.00',
    capital_distribution: '$2,375.00', capital_distribution_percentage: '4.82%',
    commission: '($25.00)', commission_percentage: '0.05%',
    total_return_amount: '$3,725.00', total_return_percentage: '7.56%', irr: '4.65%' },
  { id: 1, type: 'Stock', name: 'International Business Machines Corporation Consolidated Class A', currency: 'USD',
    current_position: '1,000.000000000', investment_date: '14-Mar-23', entry_price: '$120.50', entry_value: '$120,500.00',
    current_price: '$145.25', current_value: '$145,250.00', share_of_portfolio: '40.7%',
    price_change_percentage: '20.54%', realized_gl: '$0.00', unrealized_gl: '$24,750.00',
    capital_distribution: '$1,200.00', capital_distribution_percentage: '1.00%',
    commission: '($150.00)', commission_percentage: '0.12%',
    total_return_amount: '$25,800.00', total_return_percentage: '21.41%', irr: '12.30%' },
  { id: 7, type: 'Fund', name: 'BlackRock Global Funds - World Healthscience Fund D2', currency: 'EUR',
    current_position: '1,200.000000000', investment_date: '30-Aug-24', entry_price: '€24.15', entry_value: '€28,980.00',
    current_price: '€27.30', current_value: '€32,760.00', share_of_portfolio: '9.2%',
    price_change_percentage: '13.04%', realized_gl: '$0.00', unrealized_gl: '€3,780.00',
    capital_distribution: '€0.00', capital_distribution_percentage: '0.00%',
    commission: '(€35.00)', commission_percentage: '0.12%',
    total_return_amount: '€3,745.00', total_return_percentage: '12.92%', irr: '9.80%' },
  { id: 4, type: 'Crypto', name: 'Bitcoin', currency: 'USD',
    current_position: '0.750000000', investment_date: '09-Jan-24', entry_price: '$42,000.00', entry_value: '$31,500.00',
    current_price: '$38,400.00', current_value: '$28,800.00', share_of_portfolio: '8.1%',
    price_change_percentage: '−8.57%', realized_gl: '$0.00', unrealized_gl: '($2,700.00)',
    capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
    commission: '($40.00)', commission_percentage: '0.13%',
    total_return_amount: '($2,740.00)', total_return_percentage: '−8.70%', irr: '−15.20%' },
  { id: 2, type: 'Stock', name: 'Koninklijke Philips N.V. New York Registry Shares', currency: 'EUR',
    current_position: '2,500.000000000', investment_date: '02-Jun-23', entry_price: '€18.40', entry_value: '€46,000.00',
    current_price: '€21.10', current_value: '€52,750.00', share_of_portfolio: '14.8%',
    price_change_percentage: '14.67%', realized_gl: '$0.00', unrealized_gl: '€6,750.00',
    capital_distribution: '€500.00', capital_distribution_percentage: '1.09%',
    commission: '(€60.00)', commission_percentage: '0.13%',
    total_return_amount: '€7,190.00', total_return_percentage: '15.63%', irr: '8.90%' },
  { id: 9, type: 'ETF', name: 'Vanguard FTSE Developed Markets Index Fund ETF Shares', currency: 'GBP',
    current_position: '600.000000000', investment_date: '17-Feb-24', entry_price: '£26.80', entry_value: '£16,080.00',
    current_price: '£26.80', current_value: '£16,080.00', share_of_portfolio: '4.5%',
    price_change_percentage: '0.00%', realized_gl: '$0.00', unrealized_gl: '£0.00',
    capital_distribution: '£180.00', capital_distribution_percentage: '1.12%',
    commission: '(£12.00)', commission_percentage: '0.07%',
    total_return_amount: '£168.00', total_return_percentage: '1.04%', irr: '1.90%' },
  { id: 6, type: 'Stock', name: 'Samsung Electronics Co., Ltd. Common Shares GDR', currency: 'USD',
    current_position: '0.000000000', investment_date: '05-May-24', entry_price: '$1,350.00', entry_value: '$40,500.00',
    current_price: 'N/R', current_value: '$0.00', share_of_portfolio: '0.0%',
    price_change_percentage: 'N/R', realized_gl: '$0.00', unrealized_gl: '($40,500.00)',
    capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
    commission: '($30.00)', commission_percentage: '0.07%',
    total_return_amount: '($40,530.00)', total_return_percentage: '−100.07%', irr: '−78.40%' },
  { id: 11, type: 'Stock', name: 'Novo Nordisk A/S B Share Copenhagen', currency: 'USD',
    current_position: '150.000000000', investment_date: '12-Dec-24', entry_price: '$102.40', entry_value: '$15,360.00',
    current_price: '$74.90', current_value: '$11,235.00', share_of_portfolio: '3.1%',
    price_change_percentage: '−26.86%', realized_gl: '$0.00', unrealized_gl: '($4,125.00)',
    capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
    commission: '($18.00)', commission_percentage: '0.12%',
    total_return_amount: '($4,143.00)', total_return_percentage: '−27.00%', irr: 'N/R' },
  { id: 5, type: 'Bond', name: 'Federal National Mortgage Association 4.5% 2045', currency: 'USD',
    current_position: '200.000000000', investment_date: '08-Mar-24', entry_price: '97.25', entry_value: '$19,450.00',
    current_price: '96.10', current_value: '$19,220.00', share_of_portfolio: '5.4%',
    price_change_percentage: '−1.18%', realized_gl: '$0.00', unrealized_gl: '($230.00)',
    capital_distribution: '$4,500.00', capital_distribution_percentage: '23.14%',
    commission: '($20.00)', commission_percentage: '0.10%',
    total_return_amount: '$4,250.00', total_return_percentage: '21.85%', irr: '10.60%' },
  { id: 8, type: 'ETF', name: 'iShares MSCI Emerging Markets ETF', currency: 'USD',
    current_position: '300.000000000', investment_date: '25-Jul-24', entry_price: '$43.10', entry_value: '$12,930.00',
    current_price: '$45.80', current_value: '$13,740.00', share_of_portfolio: '3.9%',
    price_change_percentage: '6.26%', realized_gl: '$0.00', unrealized_gl: '$810.00',
    capital_distribution: '$0.00', capital_distribution_percentage: '0.00%',
    commission: '($14.00)', commission_percentage: '0.11%',
    total_return_amount: '$796.00', total_return_percentage: '6.16%', irr: 'N/R' },
  { id: 10, type: 'Cash-like', name: 'Vanity Fair Corporation 0% 2027 Zero Coupon Synthetic', currency: 'EUR',
    current_position: '80.000000000', investment_date: '19-Sep-24', entry_price: '€85.00', entry_value: '€6,800.00',
    current_price: '€85.00', current_value: '€6,800.00', share_of_portfolio: '1.9%',
    price_change_percentage: '0.00%', realized_gl: '$0.00', unrealized_gl: '€0.00',
    capital_distribution: '€0.00', capital_distribution_percentage: '0.00%',
    commission: '(€8.00)', commission_percentage: '0.12%',
    total_return_amount: '(€8.00)', total_return_percentage: '−0.12%', irr: 'N/R' },
  { id: 12, type: 'Stock', name: 'Taiwan Semiconductor Manufacturing Company ADR', currency: 'USD',
    current_position: '250.000000000', investment_date: '03-Feb-25', entry_price: '$188.20', entry_value: '$47,050.00',
    current_price: '$221.40', current_value: '$55,350.00', share_of_portfolio: '15.5%',
    price_change_percentage: '17.64%', realized_gl: '$0.00', unrealized_gl: '$8,300.00',
    capital_distribution: '$420.00', capital_distribution_percentage: '0.89%',
    commission: '($52.00)', commission_percentage: '0.11%',
    total_return_amount: '$8,668.00', total_return_percentage: '18.42%', irr: '22.10%' },
]

