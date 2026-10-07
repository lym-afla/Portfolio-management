path = 'frontend/tests/browser/fixture-server.mjs'
src = open(path, encoding='utf-8').read()

# 1. New flow flag.
old = "export async function startFixtureServer({ longAccount = false, contextFailures = false, dateFlow = false, requestFlow = false, recoveryFlow = false, d4Flow = false, chartsC2Flow = false, chartsC3Flow = false, settingsAccountFlow = false, d5States = false, importsD6Flow = false, brokersSecurityD7Flow = false } = {}) {"
new = "export async function startFixtureServer({ longAccount = false, contextFailures = false, dateFlow = false, requestFlow = false, recoveryFlow = false, d4Flow = false, chartsC2Flow = false, chartsC3Flow = false, chartsC4Flow = false, settingsAccountFlow = false, d5States = false, importsD6Flow = false, brokersSecurityD7Flow = false } = {}) {"
assert old in src, 'flow flag'
src = src.replace(old, new)

# 2. C4 scenario state next to the C2/C3 charts state.
old = """  // C2 chart negotiation scenarios: which envelope the nav endpoint serves
  // next, plus counters for the case's no-retry assertions. `hold` parks the
  // response until released (releaseWith decides the payload late).
  const charts = {
    scenario: 'v2',
    navRequests: 0,
    releaseWith: 'v2',
  }"""
new = """  // C2 chart negotiation scenarios: which envelope the nav endpoint serves
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
  const c4SecurityContext = (accountIds) => ({
    accountSelection: { type: 'all', id: null },
    accountIds: accountIds ?? [],
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
      context: c4SecurityContext(price ? [] : [1]),
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
  }"""
assert old in src, 'c4 state'
src = src.replace(old, new)

# 3. The C4 endpoint handlers, placed right after the C2/C3 nav handler block.
old = """      // ---- D4 flow: server-owned pages, held/failing details, recorded
      // mutations and a mutable reporting currency. ------------------------"""
new = """      // ---- C4 charts flow: scenario-driven breakdown and security-history
      // envelopes with recorded request counts. Everything else falls
      // through to the shared fixtures.
      if (chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && url.pathname === '/dashboard/api/get-breakdown/') {
        await readBody()
        chartsC4.breakdownRequests += 1
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, c4Scenario: chartsC4.breakdownScenario })
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(c4BreakdownEnvelope(chartsC4.breakdownScenario)))
        return
      }
      if (chartsC4Flow && requestedMethod === 'GET' && fixtureMethod === 'GET' && /\\/database\\/api\\/securities\\/\\d+\\/(price|position)-history\\/$/.test(url.pathname)) {
        requests.push({ method: fixtureMethod, actualMethod: requestedMethod, path: url.pathname, query: Object.fromEntries(url.searchParams) })
        const kind = url.pathname.endsWith('price-history/') ? 'price' : 'position'
        const securityId = Number(url.pathname.match(/securities\\/(\\d+)\\//)[1])
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify(c4SecurityHistoryEnvelope(securityId, kind, chartsC4.securityScenario)))
        return
      }

      // ---- D4 flow: server-owned pages, held/failing details, recorded
      // mutations and a mutable reporting currency. ------------------------"""
assert old in src, 'c4 handlers'
src = src.replace(old, new)

# 4. Expose the scenario state on the returned server object.
old2 = """    d4,
    charts,
    settingsAccount,"""
assert old2 in src, 'server return'
new2 = """    d4,
    charts,
    chartsC4,
    settingsAccount,"""
src = src.replace(old2, new2)

open(path, 'w', encoding='utf-8', newline='').write(src)
print('ok')
PYEOF_MARKER_UNREACHED
