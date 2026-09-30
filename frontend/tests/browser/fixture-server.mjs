import { createServer } from 'node:http'
import { createHash } from 'node:crypto'

import { resolveFixture } from './fixtures.mjs'

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

export async function startFixtureServer({ longAccount = false, contextFailures = false, dateFlow = false, requestFlow = false } = {}) {
  let releaseMutation
  let pendingMutation = false
  let currentDate = '2026-09-08'
  const requests = []
  const unmatchedRequests = []
  const sockets = new Set()
  const heldReads = new Map()
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
    releaseRead: (path) => heldReads.get(path)?.(),
    get pendingMutation() { return pendingMutation },
    releaseMutation: () => releaseMutation?.(),
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
