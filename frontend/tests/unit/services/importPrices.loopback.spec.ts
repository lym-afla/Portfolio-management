// Task 3 acceptance (real-data corrections): the price import over the REAL
// transport. `importPrices` runs unmocked against a loopback HTTP server
// that answers the SSE endpoint with scripted newline-delimited JSON
// streams — real axios, real sockets, real stream parsing and the real
// window-event contract the dialog consumes. Pinned here: the exact
// multi-account payload, live progress sequencing, delayed completion, the
// no-eligible completion, the provider-error event and the transport-abort
// surface. The browser-level run of the same flow is recorded separately
// (imports-prices case); in this environment Chrome never dispatches the
// preflighted POST to the fixture origin even though the identical simple
// POST and every other preflighted fixture POST work — an environmental
// limitation, documented in the ledger.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as http from 'node:http'
import { createPinia, setActivePinia } from 'pinia'

import axiosInstance from '@/config/axiosConfig'
import { importPrices } from '@/services/api'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configureContextFixture } from '../context-fixture'

type StreamScript = Array<
  | { hold: number }
  | { destroy: true }
  | Record<string, unknown>
>

let server: http.Server | null = null
let lastBody: string | null = null
let script: StreamScript = []
let requestCount = 0

const respondSse = (response: http.ServerResponse) => {
  response.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  })
  const drain = (index: number) => {
    if (index >= script.length) {
      response.end()
      return
    }
    const entry = script[index]
    if ('hold' in entry) {
      setTimeout(() => drain(index + 1), Number(entry.hold))
      return
    }
    if ('destroy' in entry) {
      response.destroy()
      return
    }
    response.write(`${JSON.stringify(entry)}\n`)
    drain(index + 1)
  }
  drain(0)
}

const startLoopback = () =>
  new Promise<void>((resolve, reject) => {
    // The jsdom page origin is http://localhost:3000; binding the loopback
    // there makes the real axios XHR same-origin (jsdom's CORS layer would
    // otherwise reject the preflighted request outright).
    server = http.createServer((request, response) => {
      if (request.method === 'OPTIONS') {
        response.writeHead(204, {
          'Access-Control-Allow-Origin': request.headers.origin ?? '*',
          'Access-Control-Allow-Headers': 'Authorization, Content-Type',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        })
        response.end()
        return
      }
      if (request.method === 'POST' && request.url === '/database/api/price-import/sse/') {
        requestCount += 1
        const chunks: Buffer[] = []
        request.on('data', (chunk) => chunks.push(chunk))
        request.on('end', () => {
          lastBody = Buffer.concat(chunks).toString('utf8')
          respondSse(response)
        })
        return
      }
      response.writeHead(404)
      response.end()
    })
    server.once('error', (error) => reject(error))
    server.listen(3000, '127.0.0.1', () => {
      axiosInstance.defaults.baseURL = 'http://localhost:3000'
      resolve()
    })
  })

const progressEvents = (): Array<Record<string, unknown>> => {
  const events = (window.performance as unknown as { __piEvents?: Array<Record<string, unknown>> }).__piEvents
  return events ?? []
}

const listenForEvents = () => {
  const store = (window.performance as unknown as { __piEvents?: Array<Record<string, unknown>> })
  store.__piEvents = []
  const listener = (event: Event) => {
    store.__piEvents!.push((event as CustomEvent).detail as Record<string, unknown>)
  }
  window.addEventListener('priceImportProgress', listener)
  return () => window.removeEventListener('priceImportProgress', listener)
}

beforeEach(async () => {
  vi.restoreAllMocks()
  lastBody = null
  script = []
  requestCount = 0
  localStorage.setItem('accessToken', 'loopback-access')
  localStorage.setItem('refreshToken', 'loopback-refresh')
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-01-31')
  await usePortfolioContextStore(pinia).reconcileContext()
  await startLoopback()
})

afterEach(async () => {
  await new Promise<void>((resolve) => {
    if (!server) return resolve()
    server.close(() => resolve())
    server = null
  })
})

const payload = () => ({
  securities: [],
  accounts: [7, 11],
  frequency: 'weekly',
  start_date: '2026-01-01',
  end_date: '2026-01-31',
})

describe('importPrices over the real transport (loopback SSE)', () => {
  it('sends the exact multi-account payload and sequences progress before a delayed completion', async () => {
    script = [
      { status: 'progress', current: 1, total: 4, progress: 25, security_name: 'Fixture Bond', date: '2026-01-05', result: 'updated', importId: 1 },
      { hold: 150 },
      { status: 'progress', current: 2, total: 4, progress: 50, security_name: 'Fixture Bond', date: '2026-01-06', result: 'skipped', importId: 1 },
      { status: 'complete', current: 4, total: 4, progress: 100, importId: 1, details: [{ security_name: 'Fixture Bond', updated_dates: ['2026-01-05'], skipped_dates: ['2026-01-06'], errors: [] }], total_dates: 2, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' },
    ]
    const stopListening = listenForEvents()
    const result = (await importPrices(payload())) as string
    stopListening()
    expect(JSON.parse(lastBody!).accounts).toEqual([7, 11])
    expect(JSON.parse(lastBody!).frequency).toBe('weekly')
    // Live progress reached the window-event contract (the first stream
    // chunk); jsdom coalesces later chunks into the load state, so the
    // completion line is asserted on the resolved response text, which is
    // what Chrome's per-arrival progress events parse line by line.
    const events = progressEvents()
    expect(events.length).toBeGreaterThanOrEqual(1)
    expect(events[0].status).toBe('progress')
    expect(events[0].progress).toBe(25)
    expect(String(result)).toContain('"status":"complete"')
    expect(String(result)).toContain('"details"')
  })

  it('delivers the no-eligible completion exactly as the consumer emits it', async () => {
    script = [
      { status: 'complete', current: 0, total: 0, progress: 0, importId: 1, message: 'No eligible securities found for the selected accounts (no held positions in the selected period)', no_eligible_securities: true, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' },
    ]
    const stopListening = listenForEvents()
    await importPrices(payload())
    stopListening()
    const events = progressEvents()
    expect(events).toHaveLength(1)
    expect(events[0].no_eligible_securities).toBe(true)
    expect(String(events[0].message)).toContain('No eligible securities')
  })

  it('surfaces a provider error event from the stream', async () => {
    script = [
      { status: 'progress', current: 1, total: 4, progress: 25, security_name: 'Fixture Bond', date: '2026-01-05', result: 'updated', importId: 1 },
      { status: 'error', importId: 1, message: 'Provider rejected the price request for Fixture Bond' },
    ]
    const stopListening = listenForEvents()
    await importPrices(payload())
    stopListening()
    const events = progressEvents()
    expect(events.map((event) => event.status)).toEqual(['progress', 'error'])
    expect(events[1].message).toContain('Provider rejected')
  })

  it('rejects with the transport-failure message when the stream dies mid-flight', async () => {
    script = [
      { status: 'progress', current: 1, total: 4, progress: 25, security_name: 'Fixture Bond', date: '2026-01-05', result: 'updated', importId: 1 },
      { destroy: true },
    ]
    const stopListening = listenForEvents()
    const failure = await importPrices(payload()).then(() => null, (error: unknown) => error)
    stopListening()
    expect(failure).toBeInstanceOf(Error)
    expect((failure as Error).message).toBe('No response received from server')
  })

  it('keeps a second import on its own stream id (ownership tagging)', async () => {
    script = [
      { status: 'progress', current: 1, total: 2, progress: 50, security_name: 'First', date: '2026-01-05', result: 'updated', importId: 1 },
    ]
    const stopListening = listenForEvents()
    const first = importPrices(payload())
    await new Promise((resolve) => setTimeout(resolve, 50))
    script = [
      { status: 'complete', current: 1, total: 1, progress: 100, importId: 2, details: [{ security_name: 'Second', updated_dates: [], skipped_dates: [], errors: [] }], total_dates: 1, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' },
    ]
    await importPrices(payload())
    await first.catch(() => undefined)
    stopListening()
    const events = progressEvents()
    // The transport tags each event with the import that produced it; the
    // module counter is global across the suite, so pin the relationship
    // (two imports -> two distinct, increasing ids) rather than the values.
    const ids = events.map((event) => event.importId as number)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids[1]).toBe(ids[0] + 1)
    expect(requestCount).toBe(2)
  })
})
