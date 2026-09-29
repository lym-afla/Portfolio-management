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

export async function startFixtureServer({ longAccount = false, contextFailures = false } = {}) {
  let releaseMutation
  let pendingMutation = false
  const requests = []
  const unmatchedRequests = []
  const sockets = new Set()
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
      const fixture = isContextMutation
        ? { status: 400, body: { error: url.pathname.includes('new_account') ? 'Synthetic account denied' : 'Synthetic settings denied' } }
        : resolveFixture(fixtureMethod, url.pathname, { longAccount: longAccount || contextFailures })
      if (contextFailures && fixtureMethod === 'GET' && url.pathname === '/users/api/get_account_choices/') fixture.body.options.push(['Second', { type: 'account', id: 2, display_name: 'Second synthetic account' }])
      requests.push({ method: fixtureMethod, path: url.pathname })

      if (requestedMethod === 'OPTIONS') {
        response.writeHead(204)
        response.end()
        return
      }

      for await (const _chunk of request) {
        // Drain request bodies without persisting synthetic credentials or tokens.
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
    get pendingMutation() { return pendingMutation },
    releaseMutation: () => releaseMutation?.(),
    origin: `http://127.0.0.1:${address.port}`,
    requests,
    unmatchedRequests,
    close: async () => {
      for (const socket of sockets) {
        socket.destroy()
      }
      await close(server)
    },
  }
}
