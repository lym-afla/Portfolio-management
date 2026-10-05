// D6 review round 2 — connection identity guards in the REAL useWebSocket
// composable, exercised through controlled socket instances. A superseded
// socket's open/close/error/message callbacks and its reconnect timer must
// never mutate shared state, spawn reconnects, or feed stale frames into a
// later run. Intentional disconnect and manual restart stay supported; no
// import command is ever sent automatically.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useWebSocket } from '@/composables/useWebSocket'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ isInitialized: true, accessToken: 'fixture-token' }),
}))

vi.mock('@/utils/logger', () => ({
  default: { log: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState = 0
  onopen: ((ev: unknown) => void) | null = null
  onclose: ((ev: unknown) => void) | null = null
  onerror: ((ev: unknown) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  sent: string[] = []
  closeRequested = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  // Controlled close: records the request; the test decides when (and on
  // which socket) the close event actually fires, like a real remote.
  close() {
    if (this.readyState === FakeWebSocket.CLOSED) return
    this.closeRequested = true
    this.readyState = FakeWebSocket.CLOSING
  }

  __emitOpen() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.({ type: 'open' })
  }

  __emitClose(code = 1000) {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ type: 'close', code })
  }

  __emitError() {
    this.onerror?.({ type: 'error' })
  }

  __emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

const latest = (): FakeWebSocket =>
  FakeWebSocket.instances[FakeWebSocket.instances.length - 1]

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useWebSocket connection ownership', () => {
  it('baseline: connects, delivers frames, sends on the open socket', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const first = latest()
    first.__emitOpen()
    await Promise.resolve()
    expect(ws.isConnected.value).toBe(true)

    ws.sendMessage({ type: 'start_file_import' })
    expect(first.sent).toEqual([JSON.stringify({ type: 'start_file_import' })])

    first.__emitMessage({ type: 'import_update', data: { status: 'progress' } })
    expect(ws.lastMessage.value).toEqual({
      type: 'import_update',
      data: { status: 'progress' },
    })
  })

  it('a superseded socket cannot feed messages into the current connection', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const socketA = latest()
    socketA.__emitOpen()
    await Promise.resolve()

    // Reset, then start the replacement connection and open it.
    ws.reset()
    void ws.connect()
    const socketB = latest()
    expect(socketB).not.toBe(socketA)
    socketB.__emitOpen()
    expect(ws.isConnected.value).toBe(true)

    // A's delayed completion callback: must not reach the current run.
    socketA.__emitMessage({
      type: 'import_complete',
      data: { totalTransactions: 99 },
    })
    expect(ws.lastMessage.value).toBe(null)
    expect(ws.isConnected.value).toBe(true)

    // The current socket still delivers.
    socketB.__emitMessage({ type: 'import_update', data: { status: 'progress' } })
    expect(ws.lastMessage.value).toEqual({
      type: 'import_update',
      data: { status: 'progress' },
    })
  })

  it('a delayed close of a superseded socket leaves the current connection open', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const socketA = latest()
    socketA.__emitOpen()
    await Promise.resolve()

    ws.reset()
    void ws.connect()
    const socketB = latest()
    socketB.__emitOpen()

    // A's close arrives after B is open: B stays connected, no reconnect
    // timer may create a third socket.
    socketA.__emitClose()
    expect(ws.isConnected.value).toBe(true)
    vi.advanceTimersByTime(5000)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(socketB.readyState).toBe(FakeWebSocket.OPEN)
  })

  it('a pending reconnect timer cannot replace the current connection', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const socketA = latest()
    socketA.__emitOpen()
    await Promise.resolve()

    // Unintentional close: schedules the 3s reconnect.
    socketA.__emitClose()
    expect(ws.isConnected.value).toBe(false)

    // A manual restart wins the race against the pending reconnect.
    ws.reset()
    void ws.connect()
    const socketB = latest()
    socketB.__emitOpen()
    expect(ws.isConnected.value).toBe(true)

    vi.advanceTimersByTime(5000)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(latest()).toBe(socketB)
    expect(ws.isConnected.value).toBe(true)
  })

  it('stale error callbacks cannot disturb the current connection', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const socketA = latest()
    socketA.__emitOpen()
    await Promise.resolve()

    ws.reset()
    void ws.connect()
    const socketB = latest()
    socketB.__emitOpen()

    socketA.__emitError()
    expect(ws.isConnected.value).toBe(true)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('the current connection still owns its own timeout', async () => {
    const ws = useWebSocket('/ws/transactions/')
    ws.reset() // force a fresh connection attempt past the auto-connect
    FakeWebSocket.instances = [] // drop the auto-connect socket for clarity
    const pending = ws.connect()
    const socket = latest()
    vi.advanceTimersByTime(3000)
    expect(await pending).toBe(false)
    expect(ws.isConnected.value).toBe(false)
    expect(socket.readyState).toBe(FakeWebSocket.CONNECTING)
  })

  it('intentional disconnect and manual restart stay supported without replay', async () => {
    const ws = useWebSocket('/ws/transactions/')
    const socketA = latest()
    socketA.__emitOpen()
    await Promise.resolve()

    ws.disconnect()
    expect(ws.isConnected.value).toBe(false)
    expect(socketA.closeRequested).toBe(true)
    // The close event of an intentional disconnect does not respawn anything.
    socketA.__emitClose()
    vi.advanceTimersByTime(5000)
    expect(FakeWebSocket.instances).toHaveLength(1)

    ws.reset()
    void ws.connect()
    const socketB = latest()
    socketB.__emitOpen()
    expect(ws.isConnected.value).toBe(true)
    ws.sendMessage({ type: 'stop_import' })
    expect(socketB.sent).toEqual([JSON.stringify({ type: 'stop_import' })])
    // No socket ever sent anything on its own.
    for (const instance of FakeWebSocket.instances) {
      expect(instance.sent.length).toBeLessThanOrEqual(1)
    }
  })
})
