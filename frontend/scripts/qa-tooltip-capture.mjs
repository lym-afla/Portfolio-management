// Captures a VIEWPORT-scoped screenshot with the NAV axis tooltip open at the
// representative PARTIALLY-SCROLLED position (canvas top at 242px, where the
// fixed header overlaps the chart's upper ~42px — the round-4 defect
// scenario's own scroll).
//
// agent-browser's `screenshot` command captures beyond the viewport, which
// resizes the layout, fires ECharts' globalout and silently closes the
// tooltip — every earlier "tooltip open" PNG lost it. This script dispatches
// the same two-step mouse sweep the browser test uses, verifies the tooltip
// is fully visible (hit-tested, clearing the fixed header), and only then
// captures via Page.captureScreenshot (viewport only).
//
// The test plants window.__c3CaptureTab on the exact tab it drives, so stale
// same-origin tabs can never qualify; bringToFront forces a fresh compositor
// frame before capture (background tabs capture stale pixels).
//
// Usage: node scripts/qa-tooltip-capture.mjs <cdp-url> <page-origin> <out-png> <x-fraction>

const cdpUrl = process.argv[2]
const pageOrigin = process.argv[3] || 'http://127.0.0.1:5189'
const outPath = process.argv[4]
const xFraction = Number(process.argv[5] || '0.16')
if (!outPath) {
  console.error('missing <out-png> argument')
  process.exit(2)
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

const evalIn = (sessionId, expression) =>
  send('Runtime.evaluate', { expression, returnByValue: true }, sessionId)
    .then((result) => result.result.value)

const TOOLTIP_STATE = `(() => {
  const tooltip = document.querySelector('.nav-chart-tooltip')
  if (!tooltip) return { present: false, why: 'tooltip-div' }
  const rect = tooltip.getBoundingClientRect()
  const isOverlay = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const st = getComputedStyle(n)
      if (st.position === 'fixed' || st.position === 'sticky') return true
    }
    return false
  }
  const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
  if (!canvas) return { present: false, why: 'canvas' }
  const canvasRect = canvas.getBoundingClientRect()
  const centerX = Math.round(canvasRect.left + canvasRect.width / 2)
  let headerBottom = 0
  for (let y = 2; y < Math.min(canvasRect.bottom - 1, window.innerHeight - 1); y += 2) {
    const el = document.elementFromPoint(centerX, y)
    if (el && !isOverlay(el)) { headerBottom = y; break }
  }
  const previousPointerEvents = tooltip.style.pointerEvents
  tooltip.style.pointerEvents = 'auto'
  try {
    const failures = []
    const points = []
    for (const [fx, fy, inset] of [[0, 0, 6], [1, 0, 6], [0, 1, 6], [1, 1, 6], [0.5, 0, 2], [0.5, 1, 2], [0, 0.5, 2], [1, 0.5, 2], [0.5, 0.5, 0]]) {
      points.push([rect.left + inset + (rect.width - 2 * inset) * fx, rect.top + inset + (rect.height - 2 * inset) * fy])
    }
    for (const [px, py] of points) {
      const el = document.elementFromPoint(Math.round(px), Math.round(py))
      if (!el || !(el === tooltip || tooltip.contains(el))) {
        failures.push({ px: Math.round(px), py: Math.round(py), coveredBy: el ? el.tagName + '.' + String(el.className).slice(0, 40) : 'none' })
      }
    }
    return {
      present: true,
      inViewport: rect.left >= 0 && rect.right <= window.innerWidth && rect.top >= 0 && rect.bottom <= window.innerHeight,
      fullyVisible: failures.length === 0 && Math.round(rect.top) >= headerBottom - 1,
      failures: failures.slice(0, 6),
      left: Math.round(rect.left),
      right: Math.round(rect.right),
      top: Math.round(rect.top),
      bottom: Math.round(rect.bottom),
      width: Math.round(rect.width),
      headerBottom,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    }
  } finally {
    tooltip.style.pointerEvents = previousPointerEvents
  }
})()`

ws.onopen = async () => {
  try {
    const { targetInfos } = await send('Target.getTargets')
    const pages = targetInfos.filter(
      (target) => target.type === 'page' && target.url.startsWith(pageOrigin),
    )
    console.log(`PAGE_TARGETS ${JSON.stringify(pages.map((page) => ({ url: page.url, attached: page.attached })))}`)

    const marked = []
    for (const page of pages) {
      const { sessionId } = await send('Target.attachToTarget', {
        targetId: page.targetId,
        flatten: true,
      })
      const isMarked = await evalIn(sessionId, 'window.__c3CaptureTab === true')
      if (isMarked) marked.push({ page, sessionId })
      else await send('Runtime.evaluate', { expression: 'window.scrollTo(0, 0)', returnByValue: true }, sessionId).catch(() => {})
    }
    if (marked.length === 0) throw new Error('no tab carried the test marker window.__c3CaptureTab')
    if (marked.length > 1) throw new Error(`marker found on ${marked.length} tabs; expected exactly one`)

    const { sessionId } = marked[0]
    await send('Page.enable', {}, sessionId)
    await send('Page.bringToFront', {}, sessionId)
    await new Promise((resolve) => setTimeout(resolve, 300))

    // The representative partially-scrolled position: canvas top at 242px —
    // the committed defect capture's own scroll, where the fixed header
    // overlaps the chart's top ~42px (header bottom 284).
    const scrolled = await evalIn(
      sessionId,
      `(() => {
        const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
        if (!canvas) return null
        const rect = canvas.getBoundingClientRect()
        window.scrollBy(0, rect.top - 242)
        const moved = canvas.getBoundingClientRect()
        return { x: Math.round(moved.left + moved.width * ${xFraction}), y: Math.round(moved.top + moved.height * 0.5), canvasTop: Math.round(moved.top) }
      })()`,
    )
    if (!scrolled) throw new Error('pilot canvas not found on the marked tab')
    await new Promise((resolve) => setTimeout(resolve, 150))

    const move = (x) =>
      send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y: scrolled.y, button: 'none' }, sessionId)
    await move(Math.max(1, scrolled.x - 12))
    await new Promise((resolve) => setTimeout(resolve, 80))
    await move(scrolled.x)
    await new Promise((resolve) => setTimeout(resolve, 400))

    const tooltip = await evalIn(sessionId, TOOLTIP_STATE)
    if (!tooltip.present) throw new Error(`tooltip not visible at capture time (${tooltip.why})`)
    if (!tooltip.inViewport) throw new Error(`tooltip outside the viewport: ${JSON.stringify(tooltip)}`)
    if (!tooltip.fullyVisible) throw new Error(`tooltip not fully visible (top ${tooltip.top}, headerBottom ${tooltip.headerBottom}, failures ${JSON.stringify(tooltip.failures)})`)

    const shot = await send('Page.captureScreenshot', { format: 'png' }, sessionId)
    const { writeFileSync } = await import('node:fs')
    writeFileSync(outPath, Buffer.from(shot.data, 'base64'))
    console.log(`TOOLTIP_STATE ${JSON.stringify(tooltip)}`)
    ws.close()
    process.exit(0)
  } catch (error) {
    console.error('CAPTURE_FAIL', error.message)
    process.exit(1)
  }
}
