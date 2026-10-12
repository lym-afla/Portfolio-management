// Minimal faithful reproduction of the blocked browser import flow
// (round-4 investigation). Two clean servers, no fixture machinery:
//   - origin server: serves the probe page (the page's real origin)
//   - api server: CORS-complete, records EVERY request at the top of its
//     callback (before any branch), answers the original fixture's 204
//     preflight style, and serves a scripted SSE stream
// The probe page performs, from the page's own origin to the api origin:
//   1. GET  the form path                      (control)
//   2. POST a table-like path, JSON body       (control — worked in the app)
//   3. POST the sse path, JSON body, XHR       (the blocked request)
//   4. POST the sse path, JSON body, fetch     (the blocked request, fetch)
//   5. POST the sse path, no custom headers    (simple request, no preflight)
// Run: node tests/browser/transport-repro.mjs [--fixture]
// With --fixture the API server is the REAL startFixtureServer (priceImport
// mode) instead of the clean minimal server.
import * as http from 'node:http'
import { runAgentBrowser } from './protocol.mjs'
import { startFixtureServer } from './fixture-server.mjs'

const useFixture = process.argv.includes('--fixture')
const log = (...parts) => console.log('[repro]', ...parts)

const apiArrivals = []
let apiServer = null
let apiPort = null
if (useFixture) {
  // Started below, after the flag parse, with the price-import mode.
} else {
  apiServer = http.createServer((request, response) => {
  apiArrivals.push(`${request.method} ${request.url}`)
  const cors = {
    'Access-Control-Allow-Origin': request.headers.origin ?? '*',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  }
  if (request.method === 'OPTIONS') {
    response.writeHead(204, cors)
    response.end()
    return
  }
  if (request.method === 'POST' && request.url === '/database/api/price-import/sse/') {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => {
      response.writeHead(200, { ...cors, 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
      response.write(`${JSON.stringify({ status: 'progress', current: 1, total: 2, progress: 50, importId: 1 })}\n`)
      setTimeout(() => {
        try {
          response.write(`${JSON.stringify({ status: 'complete', current: 2, total: 2, progress: 100, importId: 1 })}\n`)
          response.end()
        } catch { /* client gone */ }
      }, 200)
    })
    return
  }
  response.writeHead(200, { ...cors, 'Content-Type': 'application/json' })
  response.end(JSON.stringify({ ok: true }))
  })
}

const pageHtml = `<!doctype html><html><head><meta charset="utf-8"><title>transport probe</title></head>
<body><pre id="results">running</pre>
<script>
  const API = '%API_ORIGIN%'
  const results = {}
  const record = (name, value) => { results[name] = value; document.getElementById('results').textContent = JSON.stringify(results) }
  const done = () => document.getElementById('results').dataset.done = 'true'
  const run = async () => {
    results.api = API
    record('stage', 'start')
    // 1. GET control
    results.get = await fetch(API + '/database/api/price-import/', { headers: { Authorization: 'Bearer probe-token' } }).then((r) => r.status).catch((e) => 'failed: ' + e.message)
    record('stage', 'get')
    // 2. POST control (table-like, JSON body)
    results.postTable = await fetch(API + '/database/api/get-prices-table/', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer probe-token' }, body: JSON.stringify({ probe: 1 }) }).then((r) => r.status).catch((e) => 'failed: ' + e.message)
    record('stage', 'postTable')
    // 3. POST sse via XHR (the app's exact axios shape)
    results.xhrSse = await new Promise((resolve) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', API + '/database/api/price-import/sse/')
      xhr.setRequestHeader('Content-Type', 'application/json')
      xhr.setRequestHeader('Authorization', 'Bearer probe-token')
      xhr.onload = () => resolve('status ' + xhr.status)
      xhr.onerror = () => resolve('xhr error event')
      xhr.ontimeout = () => resolve('timeout')
      xhr.send(JSON.stringify({ probe: 1 }))
    })
    record('stage', 'xhrSse')
    // 4. POST sse via fetch (JSON body)
    results.fetchSse = await fetch(API + '/database/api/price-import/sse/', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer probe-token' }, body: JSON.stringify({ probe: 1 }) }).then((r) => r.status).catch((e) => 'failed: ' + e.message)
    record('stage', 'fetchSse')
    // 5. POST sse simple (no custom headers, no preflight); reads the 501
    // body, which carries the fixture callback's exception message.
    results.simpleSse = await fetch(API + '/database/api/price-import/sse/', { method: 'POST', body: 'simple' })
      .then(async (r) => String(r.status) + ': ' + (await r.text()).slice(0, 300))
      .catch((e) => 'failed: ' + e.message)
    record('stage', 'done')
    done()
  }
  run().catch((error) => { record('fatal', String(error)); done() })
</script></body></html>`

const originServer = http.createServer((request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
  response.end(pageHtml.replace('%API_ORIGIN%', `http://127.0.0.1:${apiPort}`))
})

const listen = (server, port) =>
  new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => resolve())
  })

let fixtureServerRef = null
if (useFixture) {
  fixtureServerRef = await startFixtureServer({ priceImportFlow: true })
  apiServer = { close: () => fixtureServerRef.close?.() ?? undefined }
  apiPort = Number(new URL(fixtureServerRef.origin).port)
  log('using the REAL fixture server (priceImportFlow)')
} else {
  await listen(apiServer, 0)
  apiPort = apiServer.address().port
}
await listen(originServer, 0)
const originPort = originServer.address().port
log('api origin:', `http://127.0.0.1:${apiPort}`, '| page origin:', `http://127.0.0.1:${originPort}`)

const session = `repro-${Date.now()}`
const run = (args) => runAgentBrowser({
  args,
  context: 'transport repro',
  session,
  log: () => {},
})

try {
  await run(['open', `http://127.0.0.1:${originPort}/probe`])
  for (let attempt = 0; attempt < 40; attempt++) {
    const state = await run(['eval', "document.getElementById('results')?.dataset.done === 'true'"])
    if (state.result === true || state === true) break
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  const results = await run(['eval', "document.getElementById('results')?.textContent"])
  log('page results:', results.result ?? results)
  await run(['close'])
} finally {
  apiServer.close()
  originServer.close()
}
log('api server arrivals:', JSON.stringify(apiArrivals, null, 1))
if (fixtureServerRef) {
  log('priceImport.requests:', JSON.stringify(fixtureServerRef.priceImport.requests, null, 1))
  log('fixture unmatched:', JSON.stringify(fixtureServerRef.unmatchedRequests, null, 1))
}
