// Captures a VIEWPORT-scoped screenshot with the ECharts axis tooltip open.
// agent-browser's own `screenshot` command captures beyond the viewport,
// which resizes the layout, fires ECharts' globalout and silently closes the
// tooltip — every earlier "tooltip open" PNG lost it. This script dispatches
// the same two-step mouse sweep the browser test uses, verifies the tooltip
// div is visible, and only then captures via Page.captureScreenshot (viewport
// only), so the tooltip cannot close before the shutter.
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

const FIND_TOOLTIP = `(() => {
  const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
  if (!canvas) return { present: false, why: 'canvas' }
  const host = canvas.parentElement.parentElement
  const tooltip = [...host.children].find(
    (child) => child.tagName === 'DIV' && !child.contains(canvas) && (child.innerText || '').trim() !== '' && child.getBoundingClientRect().width > 0,
  )
  if (!tooltip) return { present: false, why: 'tooltip-div' }
  const rect = tooltip.getBoundingClientRect()
  return {
    present: true,
    inViewport: rect.left >= 0 && rect.right <= window.innerWidth && rect.top >= 0 && rect.bottom <= window.innerHeight,
    left: Math.round(rect.left),
    right: Math.round(rect.right),
    top: Math.round(rect.top),
    bottom: Math.round(rect.bottom),
    width: Math.round(rect.width),
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
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

    const point = await evalIn(
      sessionId,
      `(() => {
        const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
        if (!canvas) return null
        canvas.scrollIntoView({ block: 'center' })
        const rect = canvas.getBoundingClientRect()
        return { x: Math.round(rect.left + rect.width * ${xFraction}), y: Math.round(rect.top + rect.height * 0.5) }
      })()`,
    )
    if (!point) throw new Error('pilot canvas not found on the marked tab')
    await new Promise((resolve) => setTimeout(resolve, 150))

    const move = (x) =>
      send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y: point.y, button: 'none' }, sessionId)
    await move(Math.max(1, point.x - 12))
    await new Promise((resolve) => setTimeout(resolve, 80))
    await move(point.x)
    await new Promise((resolve) => setTimeout(resolve, 400))

    const tooltip = await evalIn(sessionId, FIND_TOOLTIP)
    if (!tooltip.present) throw new Error(`tooltip not visible at capture time (${tooltip.why})`)
    if (!tooltip.inViewport) throw new Error(`tooltip outside the viewport: ${JSON.stringify(tooltip)}`)

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
