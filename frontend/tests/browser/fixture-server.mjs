import { createServer } from 'node:http'
import { createHash } from 'node:crypto'

import { resolveFixture } from './fixtures.mjs'
import { createImportsWs } from './imports-ws.mjs'
import {
  d4ClosedRows,
  d4ClosedTotals,
  d4FxFormStructure,
  d4OpenRows,
  d4OpenTotals,
  d4RegularDetail,
  d4RegularFormStructure,
  d4Transactions,
} from './d4-datasets.mjs'

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port ?? 0, '127.0.0.1', () => resolve())
  })
}

function close(server) {
  return new Promise((resolve, reject) => {
    // A page-held WebSocket or keep-alive socket would stall close() forever
    // (observed: an un-upgraded WS request left the raw socket open after the
    // D8 case's last page load). Drop every connection explicitly.
    try { server.closeAllConnections() } catch { }
    server.close((error) => (error ? reject(error) : resolve()))
  })
}

export async function startFixtureServer({ longAccount = false, contextFailures = false, dateFlow = false, requestFlow = false, recoveryFlow = false, d4Flow = false, chartsC2Flow = false, chartsC3Flow = false, chartsC4Flow = false, settingsAccountFlow = false, d5States = false, importsD6Flow = false, brokersSecurityD7Flow = false, port } = {}) {
  const importsWs = importsD6Flow ? createImportsWs() : null
  // D8 final-QA: phase-scoped fixture modes. The app under test bakes ONE
  // fixture origin at build time, so every QA phase shares this server and
  // flips the special flows per phase through setFixtureModes. Initial
  // values preserve the original per-case behavior exactly; several flows
  // are mutually exclusive on the same endpoints (d4 vs settings-account on
  // the settings payloads; any non-all selection context vs the C2/C4
  // chart envelopes), so only one special flow is active at a time.
  const activeModes = {
    longAccount,
    d4Flow,
    chartsC2Flow,
    chartsC3Flow,
    chartsC4Flow,
    settingsAccountFlow,
    importsD6Flow,
    brokersSecurityD7Flow,
  }
  let releaseMutation
  let pendingMutation = false
  let currentDate = '2026-09-08'
  const requests = []
  const unmatchedRequests = []
  const sockets = new Set()
  const heldReads = new Map()
  const recoveredWidgets = new Set()
  // Settings account-preservation flow state: a saved identity ABSENT from
  // the choices, server-owned selection that only changes after a confirmed
  // mutation (so save readbacks confirm like the real backend), recorded
  // write bodies and queued one-shot rejections.
  // D5 rendered-state flow: switchable populated/empty/error responses for
  // the route-family endpoints, plus GENUINE server-side search filtering
  // for the inventory lists so a no-match search is an honest
  // filtered-empty response (the case never relies on client filtering).
  const d5State = {
    mode: 'populated',
    errorPaths: new Set([
      '/summary/api/summary_data/', '/summary/api/portfolio_breakdown/',
      '/database/api/brokers/list_brokers/', '/database/api/accounts/list_accounts/',
      '/database/api/get-securities-for-database/', '/database/api/get-prices-table/',
      '/database/api/fx/list_fx/', '/users/api/user_settings_choices/', '/users/api/login/',
    ]),
    emptyBodies: {
      '/summary/api/summary_data/': { public_markets_context: { lines: [], subtotal: null, years: [] }, restricted_investments_context: { lines: [], subtotal: null, years: [] }, total_context: { line: {}, years: [] } },
      '/summary/api/portfolio_breakdown/': { consolidated_context: [], unrestricted_context: [], restricted_context: [] },
      '/database/api/brokers/list_brokers/': { items: [], totals: {}, total_items: 0, current_page: 1, total_pages: 1 },
      '/database/api/accounts/list_accounts/': { accounts: [], totals: {}, total_items: 0, current_page: 1, total_pages: 1 },
      '/database/api/get-securities-for-database/': { securities: [], total_items: 0, current_page: 1, total_pages: 1 },
      '/database/api/get-prices-table/': { prices: [], total_items: 0, current_page: 1, total_pages: 1 },
      '/database/api/fx/list_fx/': { results: [], count: 0, current_page: 1, total_pages: 1 },
    },
    // Inventory rows carry a `name`; fx rows are searched by currency codes.
    filterLists: {
      '/database/api/brokers/list_brokers/': (body, fixture) => { const q = String(body.search ?? '').toLowerCase(); if (!q) return; fixture.body.items = fixture.body.items.filter((row) => row.name.toLowerCase().includes(q)); fixture.body.total_items = fixture.body.items.length },
      '/database/api/accounts/list_accounts/': (body, fixture) => { const q = String(body.search ?? '').toLowerCase(); if (!q) return; fixture.body.accounts = fixture.body.accounts.filter((row) => row.name.toLowerCase().includes(q)); fixture.body.total_items = fixture.body.accounts.length },
      '/database/api/get-securities-for-database/': (body, fixture) => { const q = String(body.search ?? '').toLowerCase(); if (!q) return; fixture.body.securities = fixture.body.securities.filter((row) => row.name.toLowerCase().includes(q)); fixture.body.total_items = fixture.body.securities.length },
      '/database/api/fx/list_fx/': (body, fixture) => { const q = String(body.search ?? '').toLowerCase(); if (!q) return; fixture.body.results = fixture.body.results.filter((row) => `${row.from_currency}/${row.to_currency}`.toLowerCase().includes(q)); fixture.body.count = fixture.body.results.length },
    },
  }
  const settingsAccount = {
    selection: { type: 'account', id: 42 },
    dash: { table_date: '2026-09-08', default_currency: 'USD', digits: 2 },
    profileWrites: [],
    accountWrites: [],
    dashboardWrites: [],
    rejectProfileSave: false,
    rejectContextMutation: false,
    holdChoices: false,
  }
  // C2 chart negotiation scenarios: which envelope the nav endpoint serves
  // next, plus counters for the case's no-retry assertions. `hold` parks the
  // response until released (releaseWith decides the payload late).
  const charts = {
    scenario: 'v2',
    navRequests: 0,
    releaseWith: 'v2',
  }
  // C4 chart negotiation scenarios: breakdown envelope and security-history
  // envelopes switchable mid-case (eligible/signed/incomplete/legacy/
  // malformed/mismatch; security v2/legacy/malformed-price/outrange-price).
  const chartsC4 = {
    breakdownScenario: 'v2',
    securityScenario: 'v2',
    breakdownRequests: 0,
  }
  // Backend-faithful allocation documents (services/charts.py
  // build_allocation_document): one sampling period, category series with
  // money plotDivisor 1, ranked allocations, certified summary. Amounts sum
  // to the 100 denominator so eligible documents are honestly partitioning.
  const c4Context = () => ({
    accountSelection: { type: 'all', id: null },
    accountIds: [1],
    effectiveDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  })
  const c4Ok = (value, display) => ({ value, plotValue: value, status: 'ok', reason: 'observed', display })
  const c4Categories = {
    asset_type: [
      { code: 'Stocks', amount: '62' },
      { code: 'Bonds', amount: '18' },
      { code: 'Cash-like', amount: '12' },
      { code: 'Crypto', amount: '8' },
    ],
    asset_class: [
      { code: 'Equity', amount: '70' },
      { code: 'Fixed Income', amount: '18' },
      { code: 'Cash & Equivalents', amount: '12' },
    ],
    currency: [
      { code: 'USD', amount: '68' },
      { code: 'EUR', amount: '22' },
      { code: 'GBP', amount: '10' },
    ],
  }
  const c4Money = (value) => {
    const formatted = Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return `$${formatted}`
  }
  const c4Share = (amount) => c4Ok(String(Number(amount) / 100), `${Number(amount).toFixed(1)}%`)
  const c4AllocationDocument = (dimension, overrides = {}) => {
    const rows = overrides.rows ?? c4Categories[dimension]
    const denominator = overrides.denominator ?? c4Ok('100', '$100.00')
    const partial = overrides.partial ?? false
    const amounts = rows.map((row) => {
      if (partial && row.code === rows[0].code) {
        return { value: null, plotValue: null, knownSubtotal: row.amount, status: 'partial', reason: 'missing_price', display: c4Money(row.amount) }
      }
      if (overrides.signed && row.code === 'Stocks') {
        return { value: String(-Number(row.amount)), plotValue: String(-Number(row.amount)), status: 'ok', reason: 'observed', display: `(${c4Money(row.amount)})` }
      }
      return c4Ok(row.amount, c4Money(row.amount))
    })
    const shares = rows.map((row, index) => {
      if (partial && row.code === rows[0].code) {
        return { value: null, plotValue: null, status: 'unknown', reason: 'missing_price', display: '–' }
      }
      if (overrides.signed && row.code === 'Stocks') {
        return c4Ok(String(-Number(row.amount) / 100), `-${Number(row.amount).toFixed(1)}%`)
      }
      void index
      return c4Share(row.amount)
    })
    const ranked = rows
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const leftValue = Number(left.row.amount)
        const rightValue = Number(right.row.amount)
        return rightValue - leftValue || left.row.code.localeCompare(right.row.code)
      })
    const summaryOverrides = overrides.summary ?? {}
    const pieEligibility = summaryOverrides.pieEligibility ?? (partial ? 'incomplete' : overrides.signed ? 'signed' : 'eligible')
    const partition = summaryOverrides.partition ?? (pieEligibility === 'eligible' ? 'complete' : pieEligibility === 'signed' ? 'complete' : partial ? 'unknown' : 'complete')
    const totalShare = summaryOverrides.totalShare ?? (pieEligibility === 'eligible' || pieEligibility === 'signed'
      ? c4Ok('1', '100.0%')
      : { value: null, plotValue: null, status: 'not_available', reason: 'not_relevant', display: '–' })
    return {
      version: 2,
      kind: 'allocation',
      outcome: partial ? 'partial' : 'ready',
      context: c4Context(),
      periods: [
        {
          key: `allocation:${dimension}:2026-09-08`,
          endDate: '2026-09-08',
          displayLabel: '08 Sep 2026',
          interval: { startDate: '2026-09-08', endDate: '2026-09-08', kind: 'sample_interval' },
          partialPeriod: false,
        },
      ],
      series: ranked.map(({ row, index }) => ({
        id: `${dimension}:${row.code}`,
        label: row.code,
        metric: 'category_nav',
        role: 'bar',
        axis: 'money',
        unit: { kind: 'money', currency: 'USD', plotDivisor: '1' },
        points: [amounts[index]],
        category: { kind: dimension, code: row.code },
      })),
      totals: [denominator],
      allocations: ranked.map(({ row, index }, rank) => ({
        seriesId: `${dimension}:${row.code}`,
        rank: rank + 1,
        amount: amounts[index],
        share: shares[index],
      })),
      allocationSummary: {
        dimension,
        unit: { kind: 'money', currency: 'USD', plotDivisor: '1' },
        denominator,
        totalShare,
        pieEligibility,
      },
      partition,
    }
  }
  const c4BreakdownEnvelope = (scenario) => {
    const envelope = {
      assetType: { data: { Stocks: '$62.00', Bonds: '$18.00', 'Cash-like': '$12.00', Crypto: '$8.00' }, percentage: { Stocks: '62%', Bonds: '18%', 'Cash-like': '12%', Crypto: '8%' } },
      assetClass: { data: { Equity: '$70.00', 'Fixed Income': '$18.00', 'Cash & Equivalents': '$12.00' }, percentage: { Equity: '70%', 'Fixed Income': '18%', 'Cash & Equivalents': '12%' } },
      currency: { data: { USD: '$68.00', EUR: '$22.00', GBP: '$10.00' }, percentage: { USD: '68%', EUR: '22%', GBP: '10%' } },
      totalNAV: '$100.00',
      chartV2: {
        assetType: c4AllocationDocument('asset_type'),
        assetClass: c4AllocationDocument('asset_class'),
        currency: c4AllocationDocument('currency'),
      },
    }
    if (scenario === 'legacy') delete envelope.chartV2
    else if (scenario === 'malformed') envelope.chartV2.assetClass.kind = 'nav'
    else if (scenario === 'mismatch') {
      for (const document of Object.values(envelope.chartV2)) document.context.effectiveDate = '2026-01-01'
    } else if (scenario === 'signed') {
      // Stocks -25 against Bonds 125: exactly partitioning with a negative
      // position — the server certifies the pie ineligible, the table keeps
      // every signed row.
      envelope.chartV2.assetType = c4AllocationDocument('asset_type', {
        rows: [
          { code: 'Bonds', amount: '125' },
          { code: 'Stocks', amount: '25' },
        ],
        signed: true,
      })
    } else if (scenario === 'incomplete') {
      envelope.chartV2.assetType = c4AllocationDocument('asset_type', { partial: true })
    }
    return envelope
  }
  // The C4 flow never selects a local account filter, so the document scope
  // must be empty (fetchSecurityHistory strictly validates the scope since
  // the reviewer round).
  const c4SecurityContext = () => ({
    accountSelection: { type: 'all', id: null },
    accountIds: [],
    effectiveDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  })
  const c4Period = (key, iso) => ({
    key,
    endDate: iso,
    displayLabel: new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' }),
    interval: { startDate: iso, endDate: iso, kind: 'sample_interval' },
    partialPeriod: false,
  })
  const c4SecurityDocument = (securityId, kind) => {
    const price = kind === 'price'
    const rows = price
      ? [
          { key: `security:${securityId}:price:row:1`, iso: '2026-08-20', value: '101.250000', display: '$101.25' },
          { key: `security:${securityId}:price:row:2`, iso: '2026-08-27', value: '100.500000', display: '$100.50' },
          { key: `security:${securityId}:price:row:3`, iso: '2026-09-05', value: '102.250000', display: '$102.25' },
        ]
      : [
          { key: `security:${securityId}:position:opening:2026-08-01`, iso: '2026-08-01', value: '5.000000000', display: '5.000000000' },
          { key: `security:${securityId}:position:row:11`, iso: '2026-08-15', value: '8.000000000', display: '8.000000000' },
          { key: `security:${securityId}:position:row:12`, iso: '2026-08-15', value: '3.000000000', display: '3.000000000' },
          { key: `security:${securityId}:position:row:13`, iso: '2026-09-01', value: '3.000000000', display: '3.000000000' },
        ]
    return {
      version: 2,
      kind,
      outcome: 'ready',
      context: c4SecurityContext(),
      security: { id: securityId, instrumentType: 'Stock' },
      periods: rows.map((row) => c4Period(row.key, row.iso)),
      series: [
        {
          id: `security:${securityId}:${kind}`,
          label: price ? 'Price' : 'Position',
          metric: kind,
          role: 'line',
          axis: price ? 'price' : 'quantity',
          unit: price
            ? { kind: 'money', currency: 'USD', plotDivisor: '1' }
            : { kind: 'quantity', plotDivisor: '1' },
          points: rows.map((row) => c4Ok(row.value, row.display)),
        },
      ],
      partition: 'complete',
    }
  }
  const c4BondPriceDocument = (securityId) => {
    const document = c4SecurityDocument(securityId, 'price')
    document.security = { id: securityId, instrumentType: 'Bond' }
    document.series[0].unit = { kind: 'percent_of_nominal', plotDivisor: '1' }
    document.series[0].points = [
      c4Ok('99.125000', '99.125% of nominal'),
      c4Ok('99.500000', '99.5% of nominal'),
      c4Ok('99.875000', '99.875% of nominal'),
    ]
    return document
  }
  const c4CryptoPositionDocument = (securityId) => {
    const document = c4SecurityDocument(securityId, 'position')
    document.security = { id: securityId, instrumentType: 'Crypto' }
    document.series[0].points = [
      c4Ok('0.000116590', '0.000116590'),
      c4Ok('0.000216590', '0.000216590'),
      c4Ok('0.000116590', '0.000116590'),
      c4Ok('0.000216590', '0.000216590'),
    ]
    return document
  }
  const c4SecurityHistoryEnvelope = (securityId, kind, scenario) => {
    const detailBySecurity = {
      1: { instrument: 'Stock', currency: 'USD' },
      2: { instrument: 'Bond', currency: 'USD' },
      3: { instrument: 'Crypto', currency: 'USD' },
    }
    const detail = detailBySecurity[securityId] ?? { instrument: 'Stock', currency: 'USD' }
    const price = kind === 'price'
    const legacy = price
      ? [
          { date: '2026-08-20', price: 101.25 },
          { date: '2026-08-27', price: 100.5 },
          { date: '2026-09-05', price: 102.25 },
        ]
      : [
          { date: '2026-08-01', position: '5.000000000' },
          { date: '2026-08-15', position: '8.000000000' },
          { date: '2026-08-15', position: '3.000000000' },
          { date: '2026-09-01', position: '3.000000000' },
        ]
    let chartV2
    if (detail.instrument === 'Bond' && price) chartV2 = c4BondPriceDocument(securityId)
    else if (detail.instrument === 'Crypto' && !price) chartV2 = c4CryptoPositionDocument(securityId)
    else chartV2 = c4SecurityDocument(securityId, kind)
    const envelope = { legacy, chartV2 }
    if (scenario === 'legacy') return legacy
    if (scenario === `malformed-${kind}`) envelope.chartV2.version = 3
    if (scenario === `outrange-${kind}`) envelope.chartV2.series[0].points[0].plotValue = '9'.repeat(400)
    if (scenario === 'empty') {
      envelope.chartV2.outcome = 'empty'
      envelope.chartV2.periods = []
      envelope.chartV2.series = [{ ...envelope.chartV2.series[0], points: [] }]
      envelope.legacy = []
    }
    return envelope
  }
  // D4 mutation bookkeeping: positions params (server ownership), recorded
  // mutations, and a mutable reporting currency.
  const d4 = {
    mutations: [],
    positionRequests: [],
    currency: 'USD',
    deletes5: 0,
    addAttempts: 0,
  }
  const baseNavFixture = () => structuredClone(resolveFixture('GET', '/dashboard/api/get-nav-chart-data/', { longAccount: activeModes.longAccount }).body)
  const withEffectiveDate = (envelope, effectiveDate) => {
    envelope.chartV2.context.effectiveDate = effectiveDate
    return envelope
  }
  const recoveryPayloads = {
    '/dashboard/api/get-summary/': { 'Current NAV': '$100.00', Invested: '$90.00', 'Cash-out': '$0.00', total_return: '11.11%', irr: 'N/R' },
    '/dashboard/api/get-breakdown/': { assetType: { data: { Stocks: '100.00' }, percentage: { Stocks: '100%' } }, assetClass: { data: { Equity: '100.00' }, percentage: { Equity: '100%' } }, currency: { data: { USD: '100.00' }, percentage: { USD: '100%' } }, totalNAV: '$100.00' },
    '/dashboard/api/get-summary-over-time/': { lines: [{ name: 'EoP NAV', data: { YTD: '$100.00', 'All-time': '$100.00' } }], years: [], currentYear: 2026 },
    '/dashboard/api/get-nav-chart-data/': (() => {
      const envelope = structuredClone(resolveFixture('GET', '/dashboard/api/get-nav-chart-data/', { longAccount: activeModes.longAccount }).body)
      // Single-point variant matching the recovery widget's one label.
      envelope.labels = ['2026-09-08']
      envelope.datasets = envelope.datasets.map((dataset) => ({ ...dataset, data: dataset.data.slice(0, 1) }))
      envelope.chartV2.periods = envelope.chartV2.periods.slice(0, 1)
      envelope.chartV2.series = envelope.chartV2.series.map((series) => ({ ...series, points: series.points.slice(0, 1) }))
      envelope.chartV2.totals = envelope.chartV2.totals.slice(0, 1)
      return envelope
    })(),
  }
  // D7 broker/security flow: stateful broker-token records (mutation-aware),
  // recorded credential write bodies, queued save rejections and a failure
  // switch for the security resources. Synthetic credential VALUES live only
  // in the flow's form inputs; recorded bodies never go into screenshots.
  const brokersSecurityD7 = {
    tokens: {
      tinkoff_tokens: [
        { id: 11, token_type: 'read_only', sandbox_mode: false, is_active: true, created_at: '2026-09-01T10:30:00Z' },
        { id: 12, token_type: 'full_access', sandbox_mode: false, is_active: false, created_at: '2026-08-01T09:00:00Z' },
      ],
      ib_tokens: [{ id: 1 }],
      bybit_tokens: [
        { id: 21, api_key: 'bybit-synthetic-key', testnet: true, is_active: true, created_at: '2026-07-15T08:00:00Z' },
      ],
      okx_tokens: [
        { id: 31, api_key: 'okx-synthetic-key', simulated_trading: true, is_active: false, created_at: '2026-06-02T12:00:00Z' },
      ],
    },
    saveBodies: [],
    revokes: [],
    deletes: [],
    tests: [],
    rejectNextSave: false,
    failSecurityOnce: false,
    securityRequests: [],
  }
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1')
    const requestedMethod = request.method?.toUpperCase() || 'GET'
    const fixtureMethod =
      requestedMethod === 'OPTIONS'
        ? request.headers['access-control-request-method']?.toUpperCase() || 'GET'
        : requestedMethod

    response.setHeader('Access-Control-Allow-Origin', request.headers.origin || '*')
    response.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type')
    response.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS')
    response.setHeader('Cache-Control', 'no-store')

    try {
      const readBody = async () => {
        const chunks = []
        for await (const chunk of request) chunks.push(chunk)
        return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}
      }

      // ---- D6 imports flow: import-specific lookup payloads plus the
      // analyze_file envelope; everything else falls through to fixtures. --
      if (activeModes.importsD6Flow && fixtureMethod === 'GET' && url.pathname === '/database/api/brokers/') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify([
          { id: 11, name: 'Tinkoff' },
          { id: 12, name: 'Interactive Brokers' },
        ]))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }
      if (activeModes.importsD6Flow && fixtureMethod === 'GET' && url.pathname === '/database/api/accounts/') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify([
          { id: 3, name: 'Tinkoff Main', broker: { text: 'Tinkoff' } },
          { id: 9, name: 'Secondary account' },
        ]))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }
      if (activeModes.importsD6Flow && fixtureMethod === 'GET' && url.pathname === '/database/api/get-securities/') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify([
          { id: 31, name: 'ACME Corp.' },
          { id: 32, name: 'Globex Corp' },
        ]))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }
      if (activeModes.importsD6Flow && fixtureMethod === 'POST' && url.pathname === '/transactions/api/analyze_file/') {
        // Multipart body: consumed but not parsed (shape asserted by the
        // backend contract, not here).
        for await (const chunk of request) void chunk
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({
          status: 'account_identified',
          message: 'Broker account was automatically identified.',
          fileId: 'synthetic-file-1',
          identifiedAccount: { id: 3, name: 'Tinkoff Main' },
        }))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }

      // ---- C2/C3 charts flow: scenario-driven NAV envelopes with held reads.
      // Only real GETs: CORS preflights keep the generic 204 path.
      if ((activeModes.chartsC2Flow || activeModes.chartsC3Flow) && requestedMethod === 'GET' && fixtureMethod === 'GET' && url.pathname === '/dashboard/api/get-nav-chart-data/') {
        await readBody()
        charts.navRequests += 1
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, chartsScenario: charts.scenario })
        const send = (status, body) => {
          response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(body))
        }
        if (charts.scenario === 'fail500') {
          send(500, { error: { code: 'CHART_CALCULATION_FAILED', message: 'Chart data could not be calculated. Please try again.', retryable: true } })
          return
        }
        let body = baseNavFixture()
        if (charts.scenario === 'legacy') {
          delete body.chartV2
        } else if (charts.scenario === 'malformed') {
          body.chartV2.version = 3
        } else if (charts.scenario === 'mismatch') {
          body = withEffectiveDate(body, '2026-01-31')
        } else if (charts.scenario === 'outrange') {
          // Valid contract, unplotably large plotValue: the renderer boundary
          // must fail recoverably (RangeError), never silently truncate.
          body.chartV2.series[0].points[0].plotValue = '9'.repeat(400)
        } else if (charts.scenario === 'altkeys') {
          // Valid contract, DIFFERENT period keys (every key shifted a day):
          // the incompatible-refresh case — the previous viewport's keys
          // cannot map onto this document, so the controlled interaction
          // model must reset the whole window. Series identity, point count
          // and the document context stay unchanged.
          const shifted = (iso) => {
            const date = new Date(`${iso}T00:00:00Z`)
            date.setUTCDate(date.getUTCDate() - 1)
            return date.toISOString().slice(0, 10)
          }
          body.chartV2.periods = body.chartV2.periods.map((period) => ({
            ...period,
            key: `nav:${shifted(period.endDate)}`,
            endDate: shifted(period.endDate),
            interval: { ...period.interval, endDate: shifted(period.endDate) },
          }))
        } else if (charts.scenario === 'hold') {
          await new Promise((resolve) => { heldReads.set(url.pathname, resolve) })
          heldReads.delete(url.pathname)
          const released = baseNavFixture()
          if (charts.releaseWith === 'mismatch') withEffectiveDate(released, '2026-01-31')
          else if (charts.releaseWith === 'legacy') delete released.chartV2
          send(200, released)
          return
        }
        send(200, body)
        return
      }

      // ---- C4 charts flow: scenario-driven breakdown and security-history
      // envelopes with recorded request counts. Everything else falls
      // through to the shared fixtures.
      if (activeModes.chartsC4Flow && requestedMethod === 'OPTIONS') {
        // CORS preflights for routes without a base fixture (bond/crypto
        // resources) must still answer 204, like the d4 flow.
        requests.push({ method: 'OPTIONS', path: url.pathname })
        response.writeHead(204)
        response.end()
        return
      }
      if (activeModes.chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && url.pathname === '/dashboard/api/get-breakdown/') {
        await readBody()
        chartsC4.breakdownRequests += 1
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, c4Scenario: chartsC4.breakdownScenario })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(c4BreakdownEnvelope(chartsC4.breakdownScenario)))
        return
      }
      if (activeModes.chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && /^\/database\/api\/securities\/(2|3)\/$/.test(url.pathname)) {
        // Bond and crypto detail rows for the C4 unit-axis pages (the shared
        // fixture set only carries security 1).
        const securityId = Number(url.pathname.match(/securities\/(\d+)\//)[1])
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(securityId === 2
          ? {
              id: 2, instrument_type: 'Bond', ISIN: 'US0000000002', name: 'C4 Fixture Bond',
              currency: 'USD', first_investment: '01-Feb-24', open_position: '2.000000000',
              buy_in_price: '99.125000%', current_value: '$1,982.50', realized: '($17.50)',
              unrealized: '–', capital_distribution: '$87.50', irr: 'NA',
            }
          : {
              id: 3, instrument_type: 'Crypto', ISIN: 'CRYPTO:BTC', name: 'C4 Fixture Coin',
              currency: 'USD', first_investment: '01-Jan-26', open_position: '0.000216590',
              current_value: '$500.00', realized: '–', unrealized: '–',
              capital_distribution: '$500.00', irr: 'NA',
              crypto_reward_native_quantity: '0.000216590', crypto_reward_fiat_value: '500.00',
            }))
        return
      }
      if (activeModes.chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && /^\/database\/api\/securities\/(2|3)\/transactions\/$/.test(url.pathname)) {
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, query: Object.fromEntries(url.searchParams) })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ transactions: [], total_items: 0, current_page: 1, total_pages: 1 }))
        return
      }
      if (activeModes.chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && /\/database\/api\/securities\/\d+\/(price|position)-history\/$/.test(url.pathname)) {
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, query: Object.fromEntries(url.searchParams) })
        const kind = url.pathname.endsWith('price-history/') ? 'price' : 'position'
        const securityId = Number(url.pathname.match(/securities\/(\d+)\//)[1])
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(c4SecurityHistoryEnvelope(securityId, kind, chartsC4.securityScenario)))
        return
      }

      // ---- D4 flow: server-owned pages, held/failing details, recorded
      // mutations and a mutable reporting currency. ------------------------
      if (activeModes.d4Flow && requestedMethod === 'OPTIONS') {
        requests.push({ method: 'OPTIONS', path: url.pathname })
        response.writeHead(204)
        response.end()
        return
      }
      if (activeModes.d4Flow) {
        if (fixtureMethod === 'POST' && ['/open_positions/api/get_open_positions_table/', '/closed_positions/api/get_closed_positions_table/'].includes(url.pathname)) {
          const body = await readBody()
          const isOpen = url.pathname.includes('open')
          const allRows = isOpen ? d4OpenRows : d4ClosedRows
          const search = String(body.search ?? '').toLowerCase()
          // Server-side search on name/type; the SERVER ORDER is a fixed
          // shuffle that deliberately ignores the requested sort so the
          // rendered page proves display order is server-owned.
          const filtered = allRows.filter((row) =>
            !search || row.name.toLowerCase().includes(search) || row.type.toLowerCase().includes(search))
          const itemsPerPage = Number(body.itemsPerPage ?? 25) || 25
          const page = Number(body.page ?? 1) || 1
          const start = (page - 1) * itemsPerPage
          d4.positionRequests.push({ path: url.pathname, body })
          const payload = {
            [isOpen ? 'portfolio_open' : 'portfolio_closed']: filtered.slice(start, start + itemsPerPage),
            [isOpen ? 'portfolio_open_totals' : 'portfolio_closed_totals']: structuredClone(isOpen ? d4OpenTotals : d4ClosedTotals),
            total_items: filtered.length,
            current_page: page,
            total_pages: Math.max(1, Math.ceil(filtered.length / itemsPerPage)),
            cash_balances: isOpen ? { USD: '$12,500.00', EUR: '€5,100.00', GBP: '£1,150.00' } : null,
          }
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(payload))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'POST' && url.pathname === '/transactions/api/get_transactions_table/') {
          await readBody()
          // Successfully deleted transactions disappear from later listings.
          const visible = d4Transactions.filter((row) => {
            if (row.id === 'regular_5') return d4.deletes5 < 2
            if (row.id === 'fx_5') return !d4.mutations.some((m) => m.method === 'DELETE' && m.path === '/transactions/api/fx/5/')
            return true
          })
          const payload = { transactions: structuredClone(visible), total_items: visible.length, current_page: 1, total_pages: 1, currencies: ['USD', 'EUR'] }
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(payload))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/transactions/api/7/') {
          // Slow detail reply: held until the test releases it.
          await readBody()
          await new Promise((resolve) => { heldReads.set(url.pathname, resolve) })
          heldReads.delete(url.pathname)
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(structuredClone(d4RegularDetail)))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/transactions/api/8/') {
          await readBody()
          d4.mutations.push({ method: 'GET', path: url.pathname, outcome: 500 })
          response.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ detail: 'Synthetic detail failure' }))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/transactions/api/fx/5/') {
          await readBody()
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ id: 5, account: 1, date: '2026-09-01', from_currency: 'EUR', to_currency: 'USD', commission_currency: 'GBP', from_amount: '-1000.00', to_amount: '1080.00', exchange_rate: '1.08', commission: '-8.00' }))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'DELETE' && url.pathname === '/transactions/api/5/') {
          d4.deletes5 += 1
          d4.mutations.push({ method: 'DELETE', path: url.pathname, outcome: d4.deletes5 === 1 ? 400 : 204, at: Date.now() })
          if (d4.deletes5 === 1) {
            response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ detail: 'Synthetic deletion denied' }))
          } else {
            response.writeHead(204)
            response.end()
          }
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'DELETE' && url.pathname === '/transactions/api/fx/5/') {
          d4.mutations.push({ method: 'DELETE', path: url.pathname, outcome: 204 })
          response.writeHead(204)
          response.end()
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/transactions/api/form_structure/') {
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(structuredClone(d4RegularFormStructure)))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/transactions/api/fx/form_structure/') {
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(structuredClone(d4FxFormStructure)))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'POST' && url.pathname === '/transactions/api/') {
          const body = await readBody()
          d4.addAttempts += 1
          d4.mutations.push({ method: 'POST', path: url.pathname, body, outcome: d4.addAttempts === 1 ? 400 : 201 })
          if (d4.addAttempts === 1) {
            response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ quantity: ['Synthetic quantity rejection'], __all__: ['Synthetic server rejection.'] }))
          } else {
            response.writeHead(201, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ id: 99, ...body }))
          }
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && url.pathname === '/users/api/user_settings_choices/') {
          const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
          // The context strip's Reporting currency select is driven by these
          // choices; the D4 currency-reactivity flow needs a second option.
          fixture.body.currency_choices = [['USD', 'US Dollar'], ['EUR', 'Euro']]
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(fixture.body))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && ['/users/api/dashboard_settings/', '/users/api/user_settings/', '/users/api/profile/'].includes(url.pathname)) {
          const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
          if (url.pathname.includes('dashboard_settings')) {
            // The context strip's Reporting currency select binds to these
            // choices; expose EUR for the D4 currency-reactivity flow.
            fixture.body.choices.default_currency = [['USD', 'US Dollar'], ['EUR', 'Euro']]
          }
          if (d4.currency !== 'USD') {
            if (url.pathname.includes('dashboard_settings')) fixture.body.settings.default_currency = d4.currency
            else if (url.pathname.includes('user_settings')) fixture.body.default_currency = d4.currency
            else fixture.body.default_currency = d4.currency
          }
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(fixture.body))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'POST' && url.pathname === '/users/api/update_dashboard_settings/') {
          const body = await readBody()
          if (body.default_currency) d4.currency = body.default_currency
          if (body.table_date) currentDate = body.table_date
          d4.mutations.push({ method: 'POST', path: url.pathname, body: { default_currency: body.default_currency } })
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({
            table_date: body.table_date, default_currency: body.default_currency, digits: body.digits,
            requires_token_refresh: false,
          }))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
      }

      // ---- Settings account-preservation flow: saved identity missing from
      // the choices, stateful confirmed mutations, recorded write bodies and
      // queued rejections. ------------------------------------------------
      if (activeModes.settingsAccountFlow && requestedMethod === 'OPTIONS') {
        requests.push({ method: 'OPTIONS', path: url.pathname })
        response.writeHead(204)
        response.end()
        return
      }
      if (d5States && d5State.errorPaths.has(url.pathname)) {
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        if (d5State.mode === 'error') {
          if (url.pathname === '/users/api/login/') {
            response.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ detail: 'Synthetic invalid credentials' }))
          } else {
            response.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ error: 'Synthetic d5 state failure' }))
          }
          return
        }
        if (d5State.mode === 'empty') {
          const emptyBody = d5State.emptyBodies[url.pathname]
          if (emptyBody) {
            response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify(emptyBody))
            return
          }
        }
        // Populated: serve the fixture, applying genuine search filtering
        // for the inventory lists so no-match searches render an honest
        // server-owned filtered-empty response.
        const filter = d5State.filterLists[url.pathname]
        if (filter) {
          const body = await readBody()
          const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
          filter(body, fixture)
          response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(fixture.body))
          return
        }
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'GET' && url.pathname === '/users/api/user_settings/') {
        const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
        fixture.body.selected_account_type = settingsAccount.selection.type
        fixture.body.selected_account_id = settingsAccount.selection.id
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(fixture.body))
        return
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'GET' && url.pathname === '/users/api/dashboard_settings/') {
        const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
        fixture.body.settings = { ...settingsAccount.dash }
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(fixture.body))
        return
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'GET' && url.pathname === '/users/api/user_settings_choices/') {
        const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        if (settingsAccount.holdChoices) {
          settingsAccount.holdChoices = false
          await new Promise((resolve) => { heldReads.set(url.pathname, resolve) })
          heldReads.delete(url.pathname)
        }
        response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(fixture.body))
        return
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/user_settings/') {
        const body = await readBody()
        settingsAccount.profileWrites.push(body)
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        const rejected = settingsAccount.rejectProfileSave
        settingsAccount.rejectProfileSave = false
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(rejected
          ? { success: false, errors: { NAV_barchart_default_breakdown: ['Synthetic breakdown rejection'] } }
          : { success: true }))
        return
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/update_user_data_for_new_account/') {
        const body = await readBody()
        settingsAccount.accountWrites.push(body)
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        const rejected = settingsAccount.rejectContextMutation
        settingsAccount.rejectContextMutation = false
        if (rejected) {
          response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ error: 'Synthetic account denied' }))
        } else {
          // Like the real backend, the saved selection only changes after a
          // confirmed mutation, so later reads return the new identity.
          settingsAccount.selection = { type: body.type, id: body.id }
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ success: true, selected: { type: body.type, id: body.id } }))
        }
        return
      }
      if (activeModes.settingsAccountFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/update_dashboard_settings/') {
        const body = await readBody()
        settingsAccount.dashboardWrites.push(body)
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        settingsAccount.dash = { table_date: body.table_date, default_currency: body.default_currency, digits: body.digits }
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({
          table_date: body.table_date, default_currency: body.default_currency, digits: body.digits,
          requires_token_refresh: false,
        }))
        return
      }

      // ---- D7 broker/security flow: backend-faithful token endpoints with
      // recorded (never logged) write bodies, plus populated bond/crypto
      // security resources with a failure switch. -------------------------
      if (activeModes.brokersSecurityD7Flow && requestedMethod === 'OPTIONS') {
        requests.push({ method: 'OPTIONS', path: url.pathname })
        response.writeHead(204)
        response.end()
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'GET' && url.pathname === '/database/api/brokers/') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify([
          { id: 1, name: 'Tinkoff' },
          { id: 2, name: 'Interactive Brokers' },
          { id: 3, name: 'Custom Broker' },
          { id: 4, name: 'Bybit' },
          { id: 5, name: 'OKX' },
        ]))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'GET' && url.pathname === '/users/api/broker_tokens/') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(brokersSecurityD7.tokens))
        requests.push({ method: fixtureMethod, path: url.pathname })
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'POST' && url.pathname === '/users/api/tinkoff-tokens/save_read_only_token/') {
        const body = await readBody()
        brokersSecurityD7.saveBodies.push({ endpoint: 'tinkoff', body })
        requests.push({ method: fixtureMethod, path: url.pathname })
        if (brokersSecurityD7.rejectNextSave) {
          brokersSecurityD7.rejectNextSave = false
          response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ error: 'Token verification failed' }))
        } else if (body.token === 'synthetic-duplicate-token') {
          response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ message: 'This exact token is already active' }))
        } else {
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ message: 'Token saved successfully', id: 77 }))
        }
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'POST' && ['/users/api/ib-tokens/', '/users/api/bybit-tokens/', '/users/api/okx-tokens/'].includes(url.pathname)) {
        const body = await readBody()
        brokersSecurityD7.saveBodies.push({ endpoint: url.pathname, body })
        requests.push({ method: fixtureMethod, path: url.pathname })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ id: 91, message: 'Token saved successfully' }))
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'POST' && /^\/users\/api\/(tinkoff|ib)-tokens\/\d+\/test_connection\//.test(url.pathname)) {
        await readBody()
        brokersSecurityD7.tests.push(url.pathname)
        requests.push({ method: fixtureMethod, path: url.pathname })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ valid: true, message: 'Token is valid', token: { id: 11, is_active: true } }))
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'POST' && url.pathname === '/users/api/revoke_token/') {
        const body = await readBody()
        brokersSecurityD7.revokes.push(body)
        requests.push({ method: fixtureMethod, path: url.pathname })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ message: 'Token revoked successfully' }))
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'DELETE' && /^\/users\/api\/(tinkoff|ib|bybit|okx)-tokens\/\d+\/$/.test(url.pathname)) {
        const match = url.pathname.match(/^\/users\/api\/(?<provider>[a-z]+)-tokens\/(?<id>\d+)\/$/)
        const provider = `${match.groups.provider}_tokens`
        const id = Number(match.groups.id)
        const record = brokersSecurityD7.tokens[provider]?.find((token) => token.id === id)
        brokersSecurityD7.deletes.push({ path: url.pathname, provider, id })
        requests.push({ method: fixtureMethod, path: url.pathname })
        if (record && record.is_active) {
          response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify({ error: 'Cannot delete active token. Deactivate it first.' }))
          return
        }
        if (record) {
          brokersSecurityD7.tokens[provider] = brokersSecurityD7.tokens[provider].filter((token) => token.id !== id)
        }
        response.writeHead(204)
        response.end()
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'GET' && url.pathname === '/users/api/get_account_choices/') {
        const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount })
        fixture.body.options = [
          ['All accounts', { type: 'all', id: null }],
          ['Your Accounts', [
            ['Main', { type: 'account', id: 7, display_name: 'Main synthetic account' }],
          ]],
        ]
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(fixture.body))
        return
      }
      if (activeModes.brokersSecurityD7Flow && fixtureMethod === 'GET' && url.pathname.startsWith('/database/api/securities/')) {
        brokersSecurityD7.securityRequests.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) })
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname })
        const send = (status, body) => {
          response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(body))
        }
        if (brokersSecurityD7.failSecurityOnce) {
          brokersSecurityD7.failSecurityOnce = false
          send(503, { detail: 'Synthetic security resource failure' })
          return
        }
        const bondDetail = {
          id: 2,
          instrument_type: 'Bond',
          ISIN: 'US0000000002',
          name: 'Fixture Bond',
          currency: 'USD',
          first_investment: '01-Feb-24',
          open_position: '2.000000000',
          buy_in_price: '99.125000%',
          current_value: '$1,982.50',
          realized: '($17.50)',
          unrealized: '–',
          capital_distribution: '$87.50',
          irr: 'NA',
          bond_data: {
            current_notional: '2,000.00',
            is_amortizing: true,
            initial_notional: '2,400.00',
            issue_date: '2024-02-01',
            maturity_date: '2031-02-01',
            coupon_type: 'Fixed',
            credit_rating: 'AA-',
            coupon_amount: '43.75',
            coupon_rate: '4.375000%',
            coupon_frequency: 2,
            next_coupon_date: '2027-02-01',
            current_aci: { aci_amount: '2.19', aci_days: 90, total_days: 181 },
            total_aci: '25.00',
            ytm: '4.51%',
          },
        }
        const cryptoDetail = {
          id: 3,
          instrument_type: 'Crypto',
          ISIN: 'CRYPTO:BTC',
          name: 'Fixture Coin',
          currency: 'USD',
          first_investment: '01-Jan-26',
          open_position: '9007199254740993.123456789',
          current_value: '$500.00',
          realized: '–',
          unrealized: '–',
          capital_distribution: '$500.00',
          irr: 'NA',
          crypto_reward_native_quantity: '9007199254740993.123456789',
          crypto_reward_fiat_value: '500.00',
        }
        if (url.pathname === '/database/api/securities/2/') { send(200, bondDetail); return }
        if (url.pathname === '/database/api/securities/3/') { send(200, cryptoDetail); return }
        if (url.pathname === '/database/api/securities/1/') {
          send(200, {
            id: 1,
            instrument_type: 'Stock',
            ISIN: 'US0000000001',
            name: 'Fixture Stock',
            currency: 'USD',
            first_investment: '08-Sep-26',
            open_position: '10.000000000',
            buy_in_price: '101.50',
            current_price: '102.25',
            current_value: '$1,022.50',
            realized: '$12.50',
            unrealized: '$7.50',
            capital_distribution: '$0.00',
            irr: '1.25%',
          })
          return
        }
        if (/\/price-history\/$/.test(url.pathname)) { send(200, [{ date: '2025-06-01', price: '100' }]); return }
        if (/\/position-history\/$/.test(url.pathname)) { send(200, [{ date: '2025-06-01', position: '1' }]); return }
        if (/\/transactions\/$/.test(url.pathname)) {
          const idMatch = url.pathname.match(/securities\/(\d+)\/transactions\//)
          if (idMatch && idMatch[1] === '3') {
            // Crypto: characterized empty activity state.
            send(200, { transactions: [], total_items: 0 })
            return
          }
          // Distinct rows per page so the flow can assert the RENDERED rows
          // actually change with the requested page (server-owned pagination).
          const transactionsPage = Number(url.searchParams.get('page') ?? '1')
          const transactionRows = transactionsPage === 2
            ? [
                {
                  id: 11, date: '05-Feb-26', broker_account: 'Main synthetic account',
                  type: 'Sell', security: { id: 2, name: 'Page Two Instrument' },
                  quantity: '2.000000000', price: '99.875000', cash_flow: '$982.50',
                },
                {
                  id: 12, date: '18-Feb-26', broker_account: 'Main synthetic account',
                  type: 'Broker commission', cash_flow: '($2.50)',
                },
              ]
            : [
                {
                  id: 1, date: '01-Jan-26', broker_account: 'Main synthetic account',
                  type: 'Buy', security: { id: 2, name: 'Page One Instrument' },
                  quantity: '2.000000000', price: '99.125000', cash_flow: '($1,982.50)',
                },
                {
                  id: 2, date: '15-Jan-26', broker_account: 'Main synthetic account',
                  type: 'Coupon', security: { id: 2, name: 'Page One Instrument' },
                  cash_flow: '$43.75',
                },
              ]
          send(200, { transactions: transactionRows, total_items: 23 })
          return
        }
        if (url.pathname === '/database/api/securities/99/') {
          send(404, { detail: 'Not found.' })
          return
        }
        // Fall through to the generic fixtures for anything else.
      }

      const isContextMutation = contextFailures && ['/users/api/update_user_data_for_new_account/', '/users/api/update_dashboard_settings/'].includes(url.pathname)
      const dateSettingsPost = dateFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/update_dashboard_settings/'
      const dateRefreshPost = dateFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/refresh-token/'
      const fixture = isContextMutation
        ? { status: 400, body: { error: url.pathname.includes('new_account') ? 'Synthetic account denied' : 'Synthetic settings denied' } }
        : dateSettingsPost
          ? { status: 200, body: {} }
          : dateRefreshPost
            ? { status: 200, body: { access: 'fixture-new-access-token', refresh: 'fixture-new-refresh-token', effective_current_date: currentDate } }
            : resolveFixture(fixtureMethod, url.pathname, { longAccount: activeModes.longAccount || contextFailures })
      if (contextFailures && fixtureMethod === 'GET' && url.pathname === '/users/api/get_account_choices/') {
        // Append the newly available account inside the backend-faithful
        // "Your Accounts" section (the backend never emits top-level pairs).
        // id 9 keeps it unique against the base fixture's accounts 1/2 so the
        // pending-label lookup cannot match a different account.
        const accountsSection = fixture.body.options.find((entry) => entry[0] === 'Your Accounts')
        const choicesTarget = accountsSection && Array.isArray(accountsSection[1]) ? accountsSection[1] : fixture.body.options
        choicesTarget.push(['Second', { type: 'account', id: 9, display_name: 'Second synthetic account' }])
      }
      if (dateFlow && fixtureMethod === 'GET' && url.pathname === '/users/api/dashboard_settings/') fixture.body.settings.table_date = currentDate
      if (recoveryFlow && fixtureMethod === 'GET' && recoveryPayloads[url.pathname]) {
        fixture.status = recoveredWidgets.has(url.pathname) ? 200 : 503
        fixture.body = recoveredWidgets.has(url.pathname) ? recoveryPayloads[url.pathname] : { detail: 'Synthetic widget unavailable' }
      }
      const record = { method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname }
      requests.push(record)

      if (requestedMethod === 'OPTIONS') {
        response.writeHead(204)
        response.end()
        return
      }

      const requestTable = requestFlow && ['/database/api/fx/list_fx/', '/transactions/api/get_transactions_table/'].includes(url.pathname)
      const captureBody = (dateFlow && (dateSettingsPost || dateRefreshPost || url.pathname === '/open_positions/api/get_open_positions_table/')) || requestTable
      const chunks = []
      for await (const chunk of request) {
        if (captureBody) chunks.push(chunk)
      }
      if (captureBody) {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
        record.body = dateRefreshPost ? { effective_current_date: body.effective_current_date } : body
      }
      if (dateSettingsPost) {
        fixture.body = {
          table_date: record.body.table_date,
          default_currency: record.body.default_currency,
          digits: record.body.digits,
          requires_token_refresh: true,
          new_effective_date: record.body.table_date,
        }
      }
      if (dateRefreshPost) {
        currentDate = record.body.effective_current_date
        fixture.body.effective_current_date = currentDate
      }
      if (requestTable && ['GBP', 'EUR'].includes(record.body.search)) {
        const currency = record.body.search
        fixture.body = url.pathname.includes('list_fx')
          ? { results: [{ id: 1, date: '2026-09-08', from_currency: currency, to_currency: 'USD', rate: currency === 'EUR' ? '1.25' : '0.5' }], count: 1, current_page: 1, total_pages: 1 }
          : { transactions: [{ id: currency, transaction_type: 'regular', date: '08-Sep-26', type: 'Buy', security: { id: 1, name: `${currency} synthetic holding` }, quantity: '1', price: '1', cur: currency, balances: {} }], total_items: 1, current_page: 1, total_pages: 1, currencies: [currency] }
        if (currency === 'GBP') {
          await new Promise((resolve) => { heldReads.set(url.pathname, resolve) })
          heldReads.delete(url.pathname)
        }
        record.completed = true
      }
      if (isContextMutation) { pendingMutation = true; await new Promise(resolve => { releaseMutation = resolve }); pendingMutation = false }
      response.writeHead(fixture.status, { 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify(fixture.body))
    } catch (error) {
      const mismatch = { method: fixtureMethod, path: url.pathname }
      unmatchedRequests.push(mismatch)
      response.writeHead(501, { 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ detail: error.message, ...mismatch }))
    }
  })

  server.on('upgrade', (request, socket) => {
    const url = new URL(request.url, 'http://127.0.0.1')
    try {
      if (activeModes.importsD6Flow && url.pathname === '/ws/transactions/') {
        if (importsWs.state.rejectUpgrades) {
          // Deliberate failed-connect scenario: not a fixture mismatch.
          requests.push({ method: 'GET', path: url.pathname, rejected: true })
          socket.end('HTTP/1.1 501 Not Implemented\r\nConnection: close\r\n\r\n')
          return
        }
        importsWs.attach(request, socket)
        requests.push({ method: 'GET', path: url.pathname })
        return
      }
      resolveFixture('GET', url.pathname, { longAccount: activeModes.longAccount })
      const key = request.headers['sec-websocket-key']
      if (!key) {
        throw new Error('Missing Sec-WebSocket-Key')
      }
      const accept = createHash('sha1')
        .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
        .digest('base64')
      requests.push({ method: 'GET', path: url.pathname })
      socket.write(
        'HTTP/1.1 101 Switching Protocols\r\n' +
          'Upgrade: websocket\r\n' +
          'Connection: Upgrade\r\n' +
          `Sec-WebSocket-Accept: ${accept}\r\n\r\n`,
      )
      sockets.add(socket)
      socket.once('close', () => sockets.delete(socket))
    } catch {
      unmatchedRequests.push({ method: 'GET', path: url.pathname })
      socket.end('HTTP/1.1 501 Not Implemented\r\nConnection: close\r\n\r\n')
    }
  })

  await listen(server, port)
  const address = server.address()

  return {
    heldReads,
    recoverWidget: (path) => recoveredWidgets.add(path),
    resetRecovery: () => recoveredWidgets.clear(),
    releaseRead: (path) => heldReads.get(path)?.(),
    get pendingMutation() { return pendingMutation },
    releaseMutation: () => releaseMutation?.(),
    d4,
    charts,
    chartsC4,
    settingsAccount,
    d5State,
    setD5State: (mode) => { d5State.mode = mode },
    setFixtureModes: (overrides) => {
      for (const [key, value] of Object.entries(overrides ?? {})) {
        if (key in activeModes) activeModes[key] = Boolean(value)
      }
    },
    holdSettingsChoices: () => { settingsAccount.holdChoices = true },
    queueProfileRejection: () => { settingsAccount.rejectProfileSave = true },
    queueContextRejection: () => { settingsAccount.rejectContextMutation = true },
    resetSettingsAccount: () => { settingsAccount.selection = { type: 'account', id: 42 } },
    importsWs,
    brokersSecurityD7,
    origin: `http://127.0.0.1:${address.port}`,
    requests,
    unmatchedRequests,
    close: async () => {
      for (const release of heldReads.values()) release()
      for (const socket of sockets) {
        socket.destroy()
      }
      await close(server)
    },
  }
}
