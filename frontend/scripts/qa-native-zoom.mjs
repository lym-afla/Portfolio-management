// Drives the agent-browser QA browser's CDP endpoint to apply Chrome's native
// 200% page zoom metrics (Emulation.setDeviceMetricsOverride with halved CSS
// viewport and deviceScaleFactor 2 — the same metrics Ctrl+Plus produces).
const cdpUrl = process.argv[2]
const pageUrlPrefix = process.argv[3] || 'http://127.0.0.1:5189'
const method = process.argv[4] || 'zoom200' // or 'reset'

const ws = new WebSocket(cdpUrl)
let messageId = 0
const pending = new Map()
const send = (method_, params, sessionId) =>
  new Promise((resolve, reject) => {
    const id = ++messageId
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method: method_, params, sessionId }))
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

ws.onopen = async () => {
  try {
    const { targetInfos } = await send('Target.getTargets')
    const page = targetInfos.find(
      (target) => target.type === 'page' && target.url.startsWith(pageUrlPrefix),
    )
    if (!page) throw new Error(`No page target for ${pageUrlPrefix}`)
    const { sessionId } = await send('Target.attachToTarget', {
      targetId: targetId(page.targetId),
      flatten: true,
    })
    if (method === 'zoom200') {
      // 200% native zoom on a 1440x1000 window: CSS viewport halves, DPR doubles.
      await send(
        'Emulation.setDeviceMetricsOverride',
        { width: 720, height: 500, deviceScaleFactor: 2, mobile: false },
        sessionId,
      )
    } else {
      await send('Emulation.clearDeviceMetricsOverride', {}, sessionId)
    }
    console.log(`${method.toUpperCase()}_APPLIED target=${page.targetId}`)
    ws.close()
    process.exit(0)
  } catch (error) {
    console.error('CDP_FAIL', error.message)
    process.exit(1)
  }
}

function targetId(id) {
  return id
}
