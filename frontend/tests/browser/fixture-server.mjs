import { createServer } from 'node:http'
import { createHash } from 'node:crypto'

import { resolveFixture } from './fixtures.mjs'
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

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolve())
  })
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()))
  })
}

export async function startFixtureServer({ longAccount = false, contextFailures = false, dateFlow = false, requestFlow = false, recoveryFlow = false, d4Flow = false, chartsC2Flow = false, chartsC3Flow = false } = {}) {
  let releaseMutation
  let pendingMutation = false
  let currentDate = '2026-09-08'
  const requests = []
  const unmatchedRequests = []
  const sockets = new Set()
  const heldReads = new Map()
  const recoveredWidgets = new Set()
  // C2 chart negotiation scenarios: which envelope the nav endpoint serves
  // next, plus counters for the case's no-retry assertions. `hold` parks the
  // response until released (releaseWith decides the payload late).
  const charts = {
    scenario: 'v2',
    navRequests: 0,
    releaseWith: 'v2',
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
  const baseNavFixture = () => structuredClone(resolveFixture('GET', '/dashboard/api/get-nav-chart-data/', { longAccount }).body)
  const withEffectiveDate = (envelope, effectiveDate) => {
    envelope.chartV2.context.effectiveDate = effectiveDate
    return envelope
  }
  const recoveryPayloads = {
    '/dashboard/api/get-summary/': { 'Current NAV': '$100.00', Invested: '$90.00', 'Cash-out': '$0.00', total_return: '11.11%', irr: 'N/R' },
    '/dashboard/api/get-breakdown/': { assetType: { data: { Stocks: '100.00' }, percentage: { Stocks: '100%' } }, assetClass: { data: { Equity: '100.00' }, percentage: { Equity: '100%' } }, currency: { data: { USD: '100.00' }, percentage: { USD: '100%' } }, totalNAV: '$100.00' },
    '/dashboard/api/get-summary-over-time/': { lines: [{ name: 'EoP NAV', data: { YTD: '$100.00', 'All-time': '$100.00' } }], years: [], currentYear: 2026 },
    '/dashboard/api/get-nav-chart-data/': (() => {
      const envelope = structuredClone(resolveFixture('GET', '/dashboard/api/get-nav-chart-data/', { longAccount }).body)
      // Single-point variant matching the recovery widget's one label.
      envelope.labels = ['2026-09-08']
      envelope.datasets = envelope.datasets.map((dataset) => ({ ...dataset, data: dataset.data.slice(0, 1) }))
      envelope.chartV2.periods = envelope.chartV2.periods.slice(0, 1)
      envelope.chartV2.series = envelope.chartV2.series.map((series) => ({ ...series, points: series.points.slice(0, 1) }))
      envelope.chartV2.totals = envelope.chartV2.totals.slice(0, 1)
      return envelope
    })(),
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

      // ---- C2/C3 charts flow: scenario-driven NAV envelopes with held reads.
      // Only real GETs: CORS preflights keep the generic 204 path.
      if ((chartsC2Flow || chartsC3Flow) && requestedMethod === 'GET' && fixtureMethod === 'GET' && url.pathname === '/dashboard/api/get-nav-chart-data/') {
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

      // ---- D4 flow: server-owned pages, held/failing details, recorded
      // mutations and a mutable reporting currency. ------------------------
      if (d4Flow && requestedMethod === 'OPTIONS') {
        requests.push({ method: 'OPTIONS', path: url.pathname })
        response.writeHead(204)
        response.end()
        return
      }
      if (d4Flow) {
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
          const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount })
          // The context strip's Reporting currency select is driven by these
          // choices; the D4 currency-reactivity flow needs a second option.
          fixture.body.currency_choices = [['USD', 'US Dollar'], ['EUR', 'Euro']]
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(JSON.stringify(fixture.body))
          requests.push({ method: fixtureMethod, path: url.pathname })
          return
        }
        if (fixtureMethod === 'GET' && ['/users/api/dashboard_settings/', '/users/api/user_settings/', '/users/api/profile/'].includes(url.pathname)) {
          const fixture = resolveFixture(fixtureMethod, url.pathname, { longAccount })
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

      const isContextMutation = contextFailures && ['/users/api/update_user_data_for_new_account/', '/users/api/update_dashboard_settings/'].includes(url.pathname)
      const dateSettingsPost = dateFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/update_dashboard_settings/'
      const dateRefreshPost = dateFlow && fixtureMethod === 'POST' && url.pathname === '/users/api/refresh-token/'
      const fixture = isContextMutation
        ? { status: 400, body: { error: url.pathname.includes('new_account') ? 'Synthetic account denied' : 'Synthetic settings denied' } }
        : dateSettingsPost
          ? { status: 200, body: {} }
          : dateRefreshPost
            ? { status: 200, body: { access: 'fixture-new-access-token', refresh: 'fixture-new-refresh-token', effective_current_date: currentDate } }
            : resolveFixture(fixtureMethod, url.pathname, { longAccount: longAccount || contextFailures })
      if (contextFailures && fixtureMethod === 'GET' && url.pathname === '/users/api/get_account_choices/') fixture.body.options.push(['Second', { type: 'account', id: 2, display_name: 'Second synthetic account' }])
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
      resolveFixture('GET', url.pathname, { longAccount })
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

  await listen(server)
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
