import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { writeFile, mkdir } from 'node:fs/promises'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'

// Phase C rendered acceptance on the default (unflagged, modern-on) artifact:
// NAV/security/pie presentation per the owner's presentation requirements —
// chart fills its content section, zoom/reset controls without the inspection
// card, exact tables collapsed behind labelled disclosures, security
// observation pagination (25/50/100), pies without leader lines/with white
// separators/certified share labels (canvas internals are pinned by the unit
// suite; the browser case asserts the rendered surfaces and tooltips),
// "All accounts" selector, holdings context, and the devicePixelRatio
// re-initialization that keeps canvases sharp at native 200% zoom.

const here = dirname(fileURLToPath(import.meta.url))
const DESIGN_ASSETS = resolve(here, '../../../docs/design/assets/charts-c')

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 15000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const shoot = async (run, name, expectedPath) => {
  const location = await evalProbe(run, 'location.pathname')
  assert.equal(location, expectedPath, `${name}: the capture must show ${expectedPath}`)
  await run(['screenshot', resolve(DESIGN_ASSETS, name)])
}

/** True when every canvas inside the selector renders at the current
    devicePixelRatio (backing store ≈ css size × dpr) — the sharpness proof. */
const canvasDprRatios = `(() => [...document.querySelectorAll('canvas')]
  .filter((canvas) => canvas.width > 0 && canvas.getBoundingClientRect().width > 0)
  .map((canvas) => canvas.width / canvas.getBoundingClientRect().width))()`

const EXPAND = `(() => { for (const button of document.querySelectorAll('[data-testid="chart-table-toggle"], [data-testid="security-table-toggle"]')) { if (button.getAttribute('aria-expanded') === 'false') button.click() } return true })()`

async function hoverCanvasPoint(run, xFraction, yFraction = 0.5) {
  const point = await evalProbe(run, `(() => {
    const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
    if (!canvas) return { present: false }
    const rect = canvas.getBoundingClientRect()
    return {
      present: true,
      x: Math.round(rect.left + rect.width * ${xFraction}),
      y: Math.round(rect.top + rect.height * ${yFraction}),
      inView: rect.top < window.innerHeight && rect.bottom > 0,
    }
  })()`)
  assert.ok(point.present, 'pilot canvas present for tooltip hover')
  assert.ok(point.inView, 'pilot canvas in view for tooltip hover')
  await run(['mouse', 'move', String(Math.max(1, point.x - 12)), String(point.y)])
  await run(['wait', '60'])
  await run(['mouse', 'move', String(point.x), String(point.y)])
}

const waitForNavTooltip = (run) =>
  run(['wait', '--fn', `(() => { const tooltip = document.querySelector('.nav-chart-tooltip'); return !!tooltip && (tooltip.innerText || '').trim().length > 0 && tooltip.getBoundingClientRect().width > 0 })()`, '--timeout', '8000'])

async function runNativeZoom(cdpUrl, origin, percent) {
  await new Promise((resolveChild, rejectChild) => {
    const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), origin, String(percent)], { stdio: 'pipe' })
    child.on('exit', (code) => (code === 0 ? resolveChild() : rejectChild(new Error(`native zoom to ${percent}% exited ${code}`))))
    child.on('error', rejectChild)
  })
}

async function assertDashboardPhase({ run, log }) {
  // --- NAV fills its content section ---------------------------------------
  await waitFor(run, `document.querySelectorAll('[data-testid="chart-table-toggle"]').length > 0`)
  await run(['eval', EXPAND])
  await waitFor(run, `document.querySelectorAll('[data-testid="nav-echarts-pilot"] tbody tr').length > 0`)
  const geometry = await evalProbe(run, `(() => {
    const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
    const card = canvas ? canvas.closest('.v-card') : null
    if (!canvas || !card) return null
    const c = canvas.getBoundingClientRect()
    const k = card.getBoundingClientRect()
    return { canvasLeft: c.left, cardLeft: k.left, canvasRight: c.right, cardRight: k.right, canvasWidth: c.width, cardWidth: k.width, canvasHeight: c.height }
  })()`)
  assert.ok(geometry, 'NAV canvas and card found')
  assert.ok(Math.abs(geometry.canvasLeft - geometry.cardLeft) <= 2, `NAV canvas aligns with the card's left edge (${geometry.canvasLeft} vs ${geometry.cardLeft})`)
  assert.ok(geometry.canvasWidth >= geometry.cardWidth - 4, `NAV canvas fills the card width (${geometry.canvasWidth} vs ${geometry.cardWidth})`)
  assert.ok(geometry.canvasHeight >= 560, `NAV canvas matches the incumbent 600px height (${geometry.canvasHeight})`)

  // --- zoom controls without the inspection card ---------------------------
  assert.equal(await evalProbe(run, `document.querySelectorAll('.chart-inspection').length`), 0, 'the inspection card is gone')
  assert.equal(await evalProbe(run, `document.querySelectorAll('[data-testid="chart-zoom-start"], [data-testid="chart-zoom-end"]').length`), 2, 'native start/end zoom selects present')
  await run(['eval', `(() => { const select = document.querySelector('[data-testid="chart-zoom-start"]'); select.value = select.options[1].value; select.dispatchEvent(new Event('change', { bubbles: true })); return true })()`])
  await run(['wait', '150'])
  const zoomedStart = await evalProbe(run, `document.querySelector('[data-testid="chart-zoom-start"]').value`)
  assert.notEqual(zoomedStart, (await evalProbe(run, `document.querySelector('[data-testid="chart-zoom-start"] option').value`)), 'zoom start moved')
  await run(['eval', `document.querySelector('[data-testid="chart-zoom-reset"]').click()`])
  await run(['wait', '150'])
  assert.equal(await evalProbe(run, `document.querySelector('[data-testid="chart-zoom-start"]').value`), await evalProbe(run, `document.querySelector('[data-testid="chart-zoom-start"] option').value`), 'reset zoom restores the full range')

  // --- exact table disclosure ---------------------------------------------
  assert.equal(await evalProbe(run, `document.querySelector('[data-testid="chart-table-toggle"]').getAttribute('aria-expanded')`), 'true', 'NAV table expanded for the keyboard flow')
  // Keyboard inspection through the exact-data surface: Tab into the region,
  // Enter inspects the row.
  await run(['eval', `(() => { const region = document.querySelector('[data-testid="nav-echarts-pilot"] .chart-table'); region.scrollIntoView({ block: 'center' }); region.focus(); return document.activeElement === region })()`])
  await run(['press', 'Tab'])
  await run(['press', 'Enter'])
  await run(['wait', '200'])
  const inspected = await evalProbe(run, `document.querySelector('[data-testid="nav-echarts-pilot"] tbody tr[aria-selected="true"]')?.innerText ?? ''`)
  assert.match(String(inspected), /[A-Za-z]{3}-\d{2}/, 'keyboard inspection selects a row in the exact table')

  // --- simplified tooltip (real pointer hover, c3 pattern) -----------------
  await run(['eval', `(() => { const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas'); if (!canvas) return false; canvas.scrollIntoView({ block: 'center' }); window.scrollBy(0, -80); return true })()`])
  await hoverCanvasPoint(run, 0.4)
  await waitForNavTooltip(run)
  const tooltip = await evalProbe(run, `document.querySelector('.nav-chart-tooltip')?.innerText ?? ''`)
  assert.ok(String(tooltip).length > 0, 'NAV tooltip shown')
  assert.ok(!/\(USD\)|\(%\)/.test(String(tooltip)), 'tooltip carries no per-line unit suffixes')
  assert.ok(!/Portfolio NAV \(all categories\)/.test(String(tooltip)), 'tooltip carries no separate all-categories NAV line')
  assert.ok(!/Inception to /.test(String(tooltip)), 'tooltip carries no IRR horizon brackets')
  await run(['screenshot', resolve(DESIGN_ASSETS, 'charts-c-nav-tooltip.png')])
  await run(['mouse', 'move', '4', '4'])
  await run(['wait', '150'])

  // --- legend is lighter but fully operable --------------------------------
  const legendState = await evalProbe(run, `(() => {
    const button = [...document.querySelectorAll('[data-series-id]')].find((entry) => entry.getAttribute('data-series-id') === 'metric:irr_interval')
    if (!button) return null
    const before = { pressed: button.getAttribute('aria-pressed'), border: getComputedStyle(button).borderColor }
    button.click()
    return { ...before }
  })()`)
  assert.ok(legendState, 'interval IRR legend control present')
  assert.equal(legendState.pressed, 'true', 'interval IRR starts visible')
  await run(['wait', '150'])
  assert.equal(await evalProbe(run, `[...document.querySelectorAll('[data-series-id]')].find((entry) => entry.getAttribute('data-series-id') === 'metric:irr_interval').getAttribute('aria-pressed')`), 'false', 'interval IRR hides independently')
  await run(['eval', `(() => { [...document.querySelectorAll('[data-series-id]')].find((entry) => entry.getAttribute('data-series-id') === 'metric:irr_interval').click(); return true })()`])
  log('charts-c dashboard phase: geometry, zoom, disclosure, keyboard inspection, tooltip, legend verified')
}

async function assertPiePhase({ run, log }) {
  const pies = await evalProbe(run, `document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas').length`)
  assert.equal(pies, 3, 'three solid pies render')
  // The certified share labels, white separators and absent leader lines are
  // canvas-internal: pinned by the unit suite and inspected on the capture
  // below. The DOM tooltip is asserted in the mobile phase with the charts-c4
  // dispatch recipe (headless pointer sweeps do not reliably hit the pie's
  // canvas hit-test — recorded in the C4 evidence).
  await shoot(run, 'charts-c-pies.png', '/dashboard')
  log('charts-c pie phase: three pies rendered, capture taken')
}

const WAIT_CANVASES_AT = (ratio) => `(() => {
  const canvases = [...document.querySelectorAll('canvas')].filter((canvas) => canvas.getBoundingClientRect().width > 0)
  return canvases.length > 0 && canvases.every((canvas) => Math.abs(canvas.width / canvas.getBoundingClientRect().width - ${ratio}) <= 0.15)
})()`

async function assertNativeZoomPhase({ run, cdpUrl, origin, log }) {
  // The DPR watcher remounts the charts asynchronously — wait for the
  // backing stores (bounded), never a fixed sleep. One deliberate re-step:
  // a missed watcher cycle self-heals by resetting and zooming again. The
  // bounded poll reports the decisive state on failure: the case tab's own
  // devicePixelRatio vs the canvas backing ratios (a script-side dpr 2 with
  // a case-side dpr 1 would mean the keys zoomed a different target).
  const zoomTo = async (percent, ratio) => {
    await runNativeZoom(cdpUrl, origin, percent)
    const deadline = Date.now() + 8000
    let last = null
    while (Date.now() < deadline) {
      last = await evalProbe(run, `({ dpr: window.devicePixelRatio, ratios: ${canvasDprRatios} })`)
      const ratios = last?.ratios ?? []
      if (ratios.length > 0 && ratios.every((value) => Math.abs(value - ratio) <= 0.15)) return
      await new Promise((resolve) => setTimeout(resolve, 400))
    }
    await runNativeZoom(cdpUrl, origin, 100)
    await runNativeZoom(cdpUrl, origin, percent)
    const retryDeadline = Date.now() + 8000
    while (Date.now() < retryDeadline) {
      last = await evalProbe(run, `({ dpr: window.devicePixelRatio, ratios: ${canvasDprRatios} })`)
      const ratios = last?.ratios ?? []
      if (ratios.length > 0 && ratios.every((value) => Math.abs(value - ratio) <= 0.15)) return
      await new Promise((resolve) => setTimeout(resolve, 400))
    }
    throw new Error(`canvases never reached dpr ${ratio}: case-tab dpr ${last?.dpr}, ratios ${JSON.stringify(last?.ratios)}`)
  }
  await zoomTo(200, 2)
  const zoomRatios = await evalProbe(run, canvasDprRatios)
  assert.ok(zoomRatios.length > 0, 'canvases present at 200%')
  for (const ratio of zoomRatios) {
    assert.ok(Math.abs(ratio - 2) <= 0.15, `canvas backing store matches dpr 2 at native zoom (ratio ${ratio.toFixed(2)})`)
  }
  await shoot(run, 'charts-c-dashboard-200.png', '/dashboard')
  await zoomTo(100, 1)
  const resetRatios = await evalProbe(run, canvasDprRatios)
  for (const ratio of resetRatios) {
    assert.ok(Math.abs(ratio - 1) <= 0.15, `canvas backing store returns to dpr 1 after reset (ratio ${ratio.toFixed(2)})`)
  }
  log('charts-c native zoom phase: DPR re-initialization keeps canvases sharp, reset verified')
}

async function assertMobilePhase({ run, log }) {
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '400'])
  const mobile = await evalProbe(run, `(() => {
    const panel = document.querySelector('.nav-chart-panel__pilot')
    const panelRect = panel ? panel.getBoundingClientRect() : null
    const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
    const toggle = document.querySelector('[data-testid="chart-table-toggle"]')
    const zoom = document.querySelector('[data-testid="chart-zoom-reset"]')
    const hit = (element) => {
      if (!element) return false
      const rect = element.getBoundingClientRect()
      const point = document.elementFromPoint(rect.left + rect.width / 2, Math.max(rect.top + rect.height / 2, 8))
      return point === element || element.contains(point)
    }
    return {
      viewport: window.innerWidth,
      panelWidth: panelRect ? Math.round(panelRect.width) : null,
      canvasWidth: canvas ? Math.round(canvas.getBoundingClientRect().width) : null,
      toggleHittable: hit(toggle),
      zoomHittable: hit(zoom),
    }
  })()`)
  assert.equal(mobile.viewport, 390, 'viewport is 390px')
  assert.ok(mobile.panelWidth <= 390, `panel stays inside the viewport (${mobile.panelWidth}px)`)
  assert.ok(mobile.canvasWidth >= mobile.panelWidth - 8, `canvas fills the panel at 390px (${mobile.canvasWidth} vs ${mobile.panelWidth})`)
  // Hit-tests need each control scrolled into view first (a control below
  // the fold cannot be hit — that is layout, not a defect); the scroll and
  // the hit-test share one evaluation so the probe sees the settled position.
  const hits = await evalProbe(run, `(() => {
    const results = {}
    for (const [name, selector] of [['toggle', '[data-testid="chart-table-toggle"]'], ['zoom', '[data-testid="chart-zoom-reset"]']]) {
      const element = document.querySelector(selector)
      if (!element) { results[name] = false; continue }
      element.scrollIntoView({ block: 'center' })
      const rect = element.getBoundingClientRect()
      const point = document.elementFromPoint(rect.left + rect.width / 2, Math.max(rect.top + rect.height / 2, 8))
      results[name] = point === element || element.contains(point)
    }
    return results
  })()`)
  assert.equal(hits.toggle, true, 'table toggle hittable at 390px')
  assert.equal(hits.zoom, true, 'zoom reset hittable at 390px')

  // Pie tooltip at mobile, via the charts-c4 dispatch recipe: showTip drives
  // the REAL formatter + placement through the chart instance (the headless
  // pointer sweep does not reliably trigger the pie's canvas hit-test).
  const dispatched = await evalProbe(run, `(() => {
    const host = document.querySelector('[data-testid="allocation-assetType-card"] .echarts-allocation')
    if (!host || typeof host.__c4DispatchAction !== 'function') return false
    host.__c4DispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
    return true
  })()`)
  assert.ok(dispatched, 'pie dispatch hook present at mobile')
  await run(['wait', '600'])
  const pieTooltip = await evalProbe(run, `document.querySelector('.allocation-chart-tooltip')?.innerText ?? ''`)
  assert.match(String(pieTooltip), /Share:/, `pie tooltip names the share (got ${String(pieTooltip).slice(0, 120) || 'NOTHING'})`)
  assert.match(String(pieTooltip), /Full-NAV denominator:/, 'pie tooltip carries the denominator context')

  await shoot(run, 'charts-c-dashboard-390.png', '/dashboard')
  await run(['set', 'viewport', '1280', '800'])
  await run(['wait', '400'])
  const restored = await evalProbe(run, `document.querySelector('[data-testid="nav-echarts-pilot"] canvas')?.getBoundingClientRect().width ?? 0`)
  assert.ok(restored > 600, `canvas re-expands after desktop restore (${restored}px)`)
  log('charts-c mobile phase: containment, hit tests, pie tooltip, restore verified')
}

async function assertSecurityPhase({ run, fixtureServer, log }) {
  fixtureServer.chartsC4.securityScenario = 'long'
  await run(['open', `${fixtureServer.appOrigin}/database/securities/1`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)

  // Selector visibly says All accounts while unfiltered.
  const selectorLabel = await evalProbe(run, `document.querySelector('.security-account-label')?.innerText ?? document.querySelector('.v-select .v-field__input')?.innerText ?? ''`)
  assert.equal(String(selectorLabel).trim(), 'All accounts', 'unfiltered security selector visibly says All accounts')

  // Holdings context groups.
  const holdings = await evalProbe(run, `(() => {
    const section = document.querySelector('[data-testid="security-holdings"]')
    if (!section) return null
    return {
      current: section.querySelector('.holdings-group--current')?.innerText ?? '',
      previous: section.querySelector('.holdings-group--previous')?.innerText ?? '',
    }
  })()`)
  assert.ok(holdings, 'holdings section rendered')
  assert.match(holdings.current, /Currently held with/, 'current group heading')
  assert.match(holdings.current, /IBKR – Main/, 'qualified current account name')
  assert.match(holdings.previous, /Previously held with/, 'previous group heading')
  assert.match(holdings.previous, /Tinkoff – IIS/, 'qualified previous account name')

  // Observation pagination over the accepted document (60 rows).
  await run(['eval', EXPAND])
  await run(['wait', '200'])
  const pagination = await evalProbe(run, `(() => {
    const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]
    const positionTable = tables.find((table) => table.querySelectorAll('tbody tr').length > 0)
    if (!positionTable) return null
    return {
      rows: positionTable.querySelectorAll('tbody tr').length,
      range: positionTable.querySelector('[data-testid="security-table-range"]')?.innerText ?? '',
      sizes: [...positionTable.querySelectorAll('[data-testid="security-table-page-size"] option')].map((option) => option.text()),
      nextDisabled: positionTable.querySelector('[data-testid="security-table-next"]')?.disabled ?? null,
      firstKey: positionTable.querySelector('tbody tr')?.getAttribute('data-period-key') ?? '',
    }
  })()`)
  assert.ok(pagination, 'position observation table found')
  assert.equal(pagination.rows, 25, 'observation table pages 25 rows initially')
  assert.match(pagination.range, /1–25 of 60/, `range text (${pagination.range})`)
  assert.deepEqual(pagination.sizes, ['25', '50', '100'], '25/50/100 page-size choices')
  assert.equal(pagination.nextDisabled, false, 'next page available')
  await run(['eval', `(() => { const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]; const table = tables.find((t) => t.querySelectorAll('tbody tr').length > 0); table.querySelector('[data-testid="security-table-next"]').click(); return true })()`])
  await run(['wait', '150'])
  const pageTwo = await evalProbe(run, `(() => { const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]; const table = tables.find((t) => t.querySelectorAll('tbody tr').length > 0); return table.querySelector('tbody tr')?.getAttribute('data-period-key') ?? '' })()`)
  assert.match(String(pageTwo), /row:26$/, 'page two starts at observation 26')
  await run(['eval', `(() => { const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]; const table = tables.find((t) => t.querySelectorAll('tbody tr').length > 0); const select = table.querySelector('[data-testid="security-table-page-size"]'); select.value = '100'; select.dispatchEvent(new Event('change', { bubbles: true })); return true })()`])
  await run(['wait', '150'])
  const expanded = await evalProbe(run, `(() => { const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]; const table = tables.find((t) => t.querySelectorAll('tbody tr').length > 0); return { rows: table.querySelectorAll('tbody tr').length, next: table.querySelector('[data-testid="security-table-next"]').disabled } })()`)
  assert.equal(expanded.rows, 60, '100-row page shows all 60 observations')
  assert.equal(expanded.next, true, 'next disabled on the single full page')
  await shoot(run, 'charts-c-security-pagination.png', '/database/securities/1')

  // Explicit filter action: clicking the holding account filters.
  await run(['eval', `(() => { document.querySelector('[data-testid="security-holdings"] .holdings-group__filter').click(); return true })()`])
  await run(['wait', '500'])
  const filterLabel = await evalProbe(run, `document.querySelector('.security-account-label')?.innerText ?? ''`)
  assert.notEqual(String(filterLabel).trim(), 'All accounts', 'the filter click changes the selector label explicitly')
  const scopedRequest = fixtureServer.requests.filter((request) => /position-history\/$/.test(request.path)).at(-1)
  assert.equal(scopedRequest?.query?.account_id, '11', 'the filtered history request carries account_id=11')
  fixtureServer.chartsC4.securityScenario = 'v2'
  log('charts-c security phase: selector label, holdings groups, pagination, explicit filter verified')
}

/** The no-flags candidate is the shipped release configuration: every flag
    genuinely absent so the default-on policy applies (the route-loop base
    artifact is the explicit all-false rollback build). VITE_API_URL is
    inherited from run-smoke so the build binds to the live fixture server. */
async function buildChartsCArtifact(frontendRoot, artifactsDir, name) {
  const dir = resolve(artifactsDir, name)
  const flagKeys = ['VITE_NAV_ECHARTS_ENABLED', 'VITE_ALLOCATION_ECHARTS_ENABLED', 'VITE_SECURITY_ECHARTS_ENABLED']
  const previous = { ...process.env }
  for (const key of flagKeys) delete process.env[key]
  try {
    await build({ mode: 'browser-test', root: frontendRoot, build: { emptyOutDir: true, outDir: dir } })
  } finally {
    for (const key of flagKeys) {
      if (previous[key] === undefined) delete process.env[key]
      else process.env[key] = previous[key]
    }
  }
  return dir
}

export async function runChartsCFlow({ appOrigin, frontendRoot, fixtureServer, log, cdpUrl, initScript, session }) {
  const candidateDir = await buildChartsCArtifact(frontendRoot, resolve(here, 'artifacts'), 'app-charts-c-noflags')
  const candidateServer = await startBuiltAppServer(candidateDir)
  await mkdir(DESIGN_ASSETS, { recursive: true })
  fixtureServer.appOrigin = candidateServer.origin
  const run = (args) => runAgentBrowser({ args, context: `charts c ${args[0]}`, initScript, log, session })

  await run(['open', `${candidateServer.origin}/dashboard`])
  await assertDashboardPhase({ run, log })
  await shoot(run, 'charts-c-dashboard.png', '/dashboard')
  assert.ok(cdpUrl, 'cdp url available for native zoom')
  // Native zoom runs on the pristine dashboard: the mobile phase's viewport
  // emulation must not be in play when the DPR re-initialization is proven.
  await assertNativeZoomPhase({ run, cdpUrl, origin: candidateServer.origin, log })
  // The DPR re-initialization remounts every chart; a real pointer hover must
  // still drive the tooltip afterwards.
  await hoverCanvasPoint(run, 0.4)
  await waitForNavTooltip(run)
  await run(['mouse', 'move', '4', '4'])
  await run(['wait', '150'])
  await assertPiePhase({ run, log })
  await assertMobilePhase({ run, log })
  await assertSecurityPhase({ run, fixtureServer, log })

  await writeFile(
    resolve(here, 'artifacts/charts-c.json'),
    JSON.stringify({ case: 'charts-c', phases: ['dashboard', 'native-zoom', 'pies', 'mobile', 'security'], captures: DESIGN_ASSETS }, null, 2),
  )
  log('charts-c flow complete')
}
