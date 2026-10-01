// Reproduces Chrome's NATIVE browser zoom in the agent-browser QA session via
// CDP key events (Ctrl+0 reset, then Ctrl+Plus steps) — the same mechanism as
// the manual Ctrl+ scroll-wheel/keyboard zoom. Verified by devicePixelRatio
// (true native zoom changes it; CSS zoom and viewport scaling do not).
//
// Usage: node scripts/qa-native-zoom.mjs <cdp-url> <page-origin> [percent]
//   percent: 100 (reset only), 110..500 in Chrome's zoom steps; default 200.
// agent-browser's own `press Control+=` does NOT trigger zoom in headless
// Chrome; Emulation.setDeviceMetricsOverride halves the CSS viewport but left
// devicePixelRatio at 1 in this build, so it is not equivalent evidence.

const cdpUrl = process.argv[2]
const pageOrigin = process.argv[3] || 'http://127.0.0.1:5189'
const targetPercent = Number(process.argv[4] || '200')

// Chrome zoom ladder from 100%: one Ctrl+Plus per step — 110, 125, 150, 175,
// 200, 250, 300, ... (reaching 200% takes five presses).
const ZOOM_STEPS = [110, 125, 150, 175, 200, 250, 300, 400, 500]
const steps = ZOOM_STEPS.indexOf(targetPercent) + 1
if (steps < 1 && targetPercent !== 100) {
  console.error(`Unsupported zoom percent ${targetPercent}; use 100 or one of ${ZOOM_STEPS.join(', ')}`)
  process.exit(1)
}

const ws = new WebSocket(cdpUrl)
let messageId = 0
const pending = new Map()
const send = (method, params, sessionId) =>
  new Promise((resolve, reject) => {
    const id = ++messageId
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params, sessionId }))
  })

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
  }
}
ws.onerror = (error) => {
  console.error('WS_ERROR', error.message ?? error.type)
  process.exit(1)
}

const pressZoomKey = async (sessionId, virtualKeyCode) => {
  const common = {
    modifiers: 2, // Control
    windowsVirtualKeyCode: virtualKeyCode,
    nativeVirtualKeyCode: virtualKeyCode,
    code: virtualKeyCode === 48 ? 'Digit0' : 'Equal',
    key: virtualKeyCode === 48 ? '0' : '=',
  }
  await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...common }, sessionId)
  await send('Input.dispatchKeyEvent', { type: 'keyUp', ...common }, sessionId)
  await new Promise((resolve) => setTimeout(resolve, 250))
}

ws.onopen = async () => {
  try {
    const { targetInfos } = await send('Target.getTargets')
    const page = targetInfos.find(
      (target) => target.type === 'page' && target.url.startsWith(pageOrigin),
    )
    if (!page) throw new Error(`No page target for ${pageOrigin}`)
    const { sessionId } = await send('Target.attachToTarget', {
      targetId: page.targetId,
      flatten: true,
    })

    await pressZoomKey(sessionId, 48) // Ctrl+0 resets any prior zoom
    for (let index = 0; index < steps; index++) {
      await pressZoomKey(sessionId, 187) // Ctrl+Plus
    }

    const zoom = await send(
      'Runtime.evaluate',
      {
        expression: '({ dpr: window.devicePixelRatio, cssWidth: window.innerWidth, cssHeight: window.innerHeight })',
        returnByValue: true,
      },
      sessionId,
    )
    const state = zoom.result.value
    console.log(`ZOOM_STATE ${JSON.stringify(state)}`)
    const reached = Math.round(state.dpr * 100)
    ws.close()
    if (targetPercent === 100) {
      process.exit(state.dpr === 1 ? 0 : 1)
    }
    if (reached !== targetPercent) {
      console.error(`Native zoom did not reach ${targetPercent}% (devicePixelRatio ${state.dpr})`)
      process.exit(1)
    }
    process.exit(0)
  } catch (error) {
    console.error('CDP_FAIL', error.message)
    process.exit(1)
  }
}
