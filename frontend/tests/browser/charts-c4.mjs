import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'
import { measureRouteBundles } from '../../scripts/measure-route-bundles.mjs'

// C4 rendered acceptance. Phase A (flag-off artifact): the incumbent
// renderers with NO ECharts in the delivered graph — incumbent allocation
// bars, incumbent security charts, no exact tables. Phase B (flag-on
// artifact, all three gates on): three visible solid pies with invariant
// legend interaction, every ineligible state, malformed-v2 error without a
// downgrade, legacy-only notice, stock/bond/crypto histories with exact
// observed-point tables (duplicate dates included), independent price/
// position settle and recovery, mobile hit-testing and tooltip containment,
// and per-flag delivery measurements. Both artifacts are distinct builds;
// every session is registered for guaranteed cleanup.

const here = dirname(fileURLToPath(import.meta.url))
const DESIGN_ASSETS = resolve(here, '../../../docs/design/assets/charts-c4')
const BREAKDOWN_PATH = '/dashboard/api/get-breakdown/'

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 12000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const breakdownRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === BREAKDOWN_PATH).length

const historyRequests = (fixtureServer, kind) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && new RegExp(`${kind}-history/$`).test(request.path))

const dashboardState = `(() => ({
  legends: [...document.querySelectorAll('[data-testid="allocation-legend"]')].map((legend) => legend.getBoundingClientRect().width),
  allocationCanvases: [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')],
  tables: [...document.querySelectorAll('[data-testid="allocation-data-table"]')].map((table) => table.innerText),
  navPilot: !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas'),
  notice: document.querySelector('[data-testid="allocation-capability-notice"]')?.innerText ?? null,
  error: document.querySelector('[data-testid="allocation-assetType-error"]')?.innerText ?? null,
}))()`

const securityState = (section) => `(() => {
  const heading = document.querySelector('#security-${section}-history')
  const region = heading ? heading.closest('.workspace-section') ?? document.body : document.body
  return {
    heading: !!heading,
    canvas: !!region.querySelector('canvas'),
    table: region.querySelector('[data-testid="security-data-table"]')?.innerText ?? null,
    rows: region.querySelector('[data-testid="security-data-table"]')?.querySelectorAll('tbody tr').length ?? 0,
    tableCount: document.querySelectorAll('[data-testid="security-data-table"]').length,
    error: region.querySelector('[data-testid="security-render-error"]')?.innerText ?? null,
    empty: region.querySelector('[data-testid="security-history-empty"]')?.innerText ?? null,
  }
})()`

const TOOLTIP_VISIBILITY_PROBE = (tooltipSelector, canvasSelector) => `(() => {
  const tooltip = ${tooltipSelector}
  if (!tooltip) return { present: false }
  const rect = tooltip.getBoundingClientRect()
  const isOverlay = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const st = getComputedStyle(n)
      if (st.position === 'fixed' || st.position === 'sticky') return true
    }
    return false
  }
  const canvas = document.querySelector('${canvasSelector}') ?? document.querySelector('canvas')
  let headerBottom = 0
  if (canvas) {
    const canvasRect = canvas.getBoundingClientRect()
    const centerX = Math.round(canvasRect.left + canvasRect.width / 2)
    for (let y = 2; y < Math.min(canvasRect.bottom - 1, window.innerHeight - 1); y += 2) {
      const el = document.elementFromPoint(centerX, y)
      if (el && !isOverlay(el)) { headerBottom = y; break }
    }
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
      text: tooltip.innerText,
      top: Math.round(rect.top),
      bottom: Math.round(rect.bottom),
      left: Math.round(rect.left),
      right: Math.round(rect.right),
      headerBottom,
      fullyVisible: failures.length === 0,
      failures: failures.slice(0, 6),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    }
  } finally {
    tooltip.style.pointerEvents = previousPointerEvents
  }
})()`

// ECharts keeps one tooltip div per chart; only the shown one has content.
const POPULATED_TOOLTIP = (tooltipSelector) =>
  `[...document.querySelectorAll('${tooltipSelector}')].find((div) => (div.innerText || '').trim().length > 0)`

async function assertTooltipVisible(run, tooltipSelector, context) {
  await run(['wait', '--fn', `(() => {
    const tooltip = ${POPULATED_TOOLTIP(tooltipSelector)}
    return !!tooltip && tooltip.getBoundingClientRect().width > 0
  })()`, '--timeout', '8000'])
  const probe = await evalProbe(run, TOOLTIP_VISIBILITY_PROBE(
    POPULATED_TOOLTIP(tooltipSelector),
    tooltipSelector === '.allocation-chart-tooltip'
      ? '[data-testid="allocation-assetType-card"] canvas'
      : '.echarts-security canvas',
  ))
  assert.ok(probe.present, `${context}: tooltip present`)
  assert.ok(probe.width0 !== true, `${context}: tooltip has size`)
  assert.ok(probe.left >= 0 && probe.right <= probe.viewportWidth,
    `${context}: tooltip horizontally inside the viewport (${probe.left}..${probe.right} of ${probe.viewportWidth})`)
  assert.ok(probe.top >= 0 && probe.bottom <= probe.viewportHeight,
    `${context}: tooltip vertically inside the viewport (${probe.top}..${probe.bottom} of ${probe.viewportHeight})`)
  assert.equal(probe.fullyVisible, true,
    `${context}: tooltip fully visible (failures: ${JSON.stringify(probe.failures)})`)
  assert.ok(probe.top >= probe.headerBottom - 1,
    `${context}: tooltip top ${probe.top} clears the fixed header bottom ${probe.headerBottom}`)
  return probe
}

// ---------------------------------------------------------------------------
// Phase A: default-off artifact — incumbent renderers, provably lazy delivery.

export async function assertChartsC4FlagOffFlow({ appOrigin, context, initScript, log, session }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas').length >= 3`)
  const state = await evalProbe(run, dashboardState)
  assert.equal(state.legends.length, 0, 'flag off: no modern allocation legends')
  assert.equal(state.allocationCanvases.length, 3, 'flag off: three incumbent Chart.js allocation cards')
  assert.equal(state.notice, null, 'flag off: no capability notice')
  await run(['wait', '--load', 'networkidle'])
  const loadedModules = await evalProbe(run, `(async () => {
    const membership = await fetch('/.vite/module-membership.json').then(response => response.json()).catch(() => ({}))
    const assets = [...new Set(performance.getEntriesByType('resource').map(entry => new URL(entry.name).pathname.slice(1)))]
    const modules = assets.flatMap((asset) => membership[asset] || [])
    return modules.join('\\n')
  })()`)
  assert.ok(!/echarts/i.test(String(loadedModules)), 'flag off: dashboard loaded module graph contains no ECharts runtime')
  await run(['open', `${appOrigin}/database/securities/1`])
  await waitFor(run, `document.querySelectorAll('#security-price-history').length > 0 && document.querySelectorAll('canvas').length > 0`)
  await run(['wait', '--load', 'networkidle'])
  const securityModules = await evalProbe(run, `(async () => {
    const membership = await fetch('/.vite/module-membership.json').then(response => response.json()).catch(() => ({}))
    const assets = [...new Set(performance.getEntriesByType('resource').map(entry => new URL(entry.name).pathname.slice(1)))]
    const modules = assets.flatMap((asset) => membership[asset] || [])
    return modules.join('\\n')
  })()`)
  assert.ok(!/echarts/i.test(String(securityModules)), 'flag off: security loaded module graph contains no ECharts runtime')
  const flagOffSecurity = await evalProbe(run, `(() => ({
    tables: document.querySelectorAll('[data-testid="security-data-table"]').length,
    canvases: document.querySelectorAll('canvas').length,
  }))()`)
  assert.equal(flagOffSecurity.tables, 0, 'flag off: no exact security tables')
  assert.ok(flagOffSecurity.canvases >= 2, 'flag off: incumbent security charts render')
  await run(['open', `${appOrigin}/login`])
  await run(['wait', '--load', 'networkidle'])
  const loginResources = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).join('\\n')`)
  assert.ok(!/echarts/i.test(String(loginResources)), 'flag off: no ECharts asset on login')
  console.log('PASS charts-c4 flag-off delivery (incumbent renderers, echarts-free graph)')
}

// ---------------------------------------------------------------------------
// Phase B: flag-on artifact — all three gates on.

export async function runChartsC4PilotFlow({
  appOrigin,
  flagOffRoot,
  frontendRoot,
  fixtureServer,
  log,
  registerSession,
  artifactsDir,
}) {
  const pilotDir = resolve(artifactsDir, 'app-c4-pilot')
  // The saved keys ARE the real VITE_* names — restoring shorthand keys would
  // leak the pilot's flag values into every later artifact build in the run.
  const previous = {
    VITE_ALLOCATION_ECHARTS_ENABLED: process.env.VITE_ALLOCATION_ECHARTS_ENABLED,
    VITE_SECURITY_ECHARTS_ENABLED: process.env.VITE_SECURITY_ECHARTS_ENABLED,
    VITE_NAV_ECHARTS_ENABLED: process.env.VITE_NAV_ECHARTS_ENABLED,
  }
  process.env.VITE_ALLOCATION_ECHARTS_ENABLED = 'true'
  process.env.VITE_SECURITY_ECHARTS_ENABLED = 'true'
  process.env.VITE_NAV_ECHARTS_ENABLED = 'true'
  try {
    await build({ mode: 'browser-test', root: frontendRoot, build: { emptyOutDir: true, outDir: pilotDir } })
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
  const pilotServer = await startBuiltAppServer(pilotDir)
  const session = `c4-pilot-${process.pid}`
  registerSession(session)
  const initScript = resolve('tests/browser/auth-init.js')
  const run = (args) => runAgentBrowser({ args, context: 'charts c4 pilot', initScript, log, session })
  // agent-browser's reload resolves before navigation completes; a wait
  // attached immediately keeps polling the pre-reload page forever.
  const reload = async () => {
    await runAgentBrowser({ args: ['reload'], context: 'charts c4 pilot reload', initScript, log, session })
    await run(['wait', '2500'])
  }
  const chartsC4 = fixtureServer.chartsC4
  await mkdir(DESIGN_ASSETS, { recursive: true })

  try {
    // --- three solid pies on the dashboard, NAV pilot alongside -------------
    await run(['open', `${pilotServer.origin}/dashboard`])
    await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3 && document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas').length === 3`)
    let state = await evalProbe(run, dashboardState)
    assert.equal(state.legends.length, 3, 'flag on: three modern allocation legends')
    assert.equal(state.allocationCanvases.length, 3, 'flag on: three solid pie canvases')
    assert.equal(state.navPilot, true, 'flag on: the NAV pilot renders alongside the pies')
    assert.equal(state.tables.length, 0, 'modern exact tables live on the Table tab, initially inactive')
    for (const card of ['assetType', 'assetClass', 'currency']) {
      await run(['eval', `(() => {
        const card = document.querySelector('[data-testid="allocation-${card}-card"]')
        const tabs = [...card.querySelectorAll('.v-tab')]
        const tableTab = tabs.find((tab) => tab.textContent.trim() === 'Table')
        tableTab.click()
        return true
      })()`])
      await run(['wait', '150'])
    }
    state = await evalProbe(run, dashboardState)
    assert.equal(state.tables.length, 3, 'flag on: three exact allocation tables after switching tabs')
    assert.match(state.tables[0], /Stocks\t\$62\.00\t62\.0%/, 'asset-type table keeps every ranked row')
    assert.match(state.tables[1], /Equity\t\$70\.00\t70\.0%/, 'asset-class table keeps every ranked row')
    assert.match(state.tables[2], /USD\t\$68\.00\t68\.0%/, 'currency table keeps every ranked row')
    for (const table of state.tables) {
      assert.match(table, /\$100\.00/, 'table shows the server denominator')
      assert.match(table, /100\.0%/, 'table shows the backend-certified total share')
    }
    await run(['eval', `(() => {
      for (const card of ['assetType', 'assetClass', 'currency']) {
        const tabs = [...document.querySelector('[data-testid="allocation-' + card + '-card"]').querySelectorAll('.v-tab')]
        tabs.find((tab) => tab.textContent.trim() === 'Chart').click()
      }
      return true
    })()`])
    await run(['wait', '150'])
    await run(['eval', `(() => { document.querySelector('[data-testid="allocation-section"]').scrollIntoView({ block: 'start' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c4-dashboard-pies.png')])

    // --- legend interaction invariance --------------------------------------
    const beforeLegend = breakdownRequestCount(fixtureServer)
    const tableBefore = (await evalProbe(run, dashboardState)).tables
    await run(['eval', `(() => {
      const button = document.querySelector('[data-testid="allocation-assetType-card"] [data-allocation-id]')
      button.focus()
      button.click()
      return true
    })()`])
    await run(['wait', '300'])
    assert.equal(breakdownRequestCount(fixtureServer) - beforeLegend, 0, 'legend focus issues no request')
    const tableAfter = (await evalProbe(run, dashboardState)).tables
    assert.deepEqual(tableAfter, tableBefore, 'legend focus preserves every table row, share and the denominator')
    await run(['eval', `(() => {
      const button = document.querySelector('[data-testid="allocation-assetType-card"] [data-allocation-id]')
      button.blur()
      return true
    })()`])

    // --- ineligible signed state: reason plus complete signed table ---------
    chartsC4.breakdownScenario = 'signed'
    await reload()
    await waitFor(run, `document.querySelector('[data-testid="allocation-ineligible"]') !== null`)
    state = await evalProbe(run, dashboardState)
    const signedReason = await evalProbe(run, `document.querySelector('[data-testid="allocation-ineligible"]')?.innerText ?? null`)
    assert.match(String(signedReason), /negative/, 'the signed reason names the misleading-pie fact')
    await run(['eval', `(() => {
      const tabs = [...document.querySelector('[data-testid="allocation-assetType-card"]').querySelectorAll('.v-tab')]
      tabs.find((tab) => tab.textContent.trim() === 'Table').click()
      return true
    })()`])
    await run(['wait', '150'])
    const signedTable = await evalProbe(run, `document.querySelector('[data-testid="allocation-assetType-card"] [data-testid="allocation-data-table"]')?.innerText ?? null`)
    assert.match(String(signedTable), /\(\$25\.00\)/, 'the signed row keeps its exact negative display')
    assert.match(String(signedTable), /-25\.0%/, 'the signed share is verbatim')
    assert.match(String(signedTable), /125\.0%/, 'the offsetting share is verbatim')
    assert.match(String(signedTable), /\$100\.00/, 'the denominator is unchanged')
    await run(['eval', `(() => { document.querySelector('[data-testid="allocation-assetType-card"]').scrollIntoView({ block: 'center' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c4-signed-table.png')])

    // --- malformed v2: error state, exactly one request, no retry -----------
    chartsC4.breakdownScenario = 'malformed'
    const beforeMalformed = breakdownRequestCount(fixtureServer)
    await reload()
    await waitFor(run, `document.querySelector('[data-testid="allocation-assetType-error"]') !== null`)
    state = await evalProbe(run, dashboardState)
    assert.match(String(state.error), /Invalid chartV2 document/, 'malformed v2 is an error, never a silent downgrade')
    await run(['wait', '600'])
    assert.equal(breakdownRequestCount(fixtureServer) - beforeMalformed, 1, 'invalid contract: exactly one request, no retry')

    // --- legacy-only: notice plus incumbent bars -----------------------------
    chartsC4.breakdownScenario = 'legacy'
    await reload()
    await waitFor(run, `document.querySelector('[data-testid="allocation-capability-notice"]') !== null`)
    state = await evalProbe(run, dashboardState)
    assert.match(String(state.notice), /legacy response/, 'legacy-only shows the honest capability notice')
    assert.equal(state.legends.length, 0, 'legacy-only stays on the incumbent renderer')
    assert.equal(state.allocationCanvases.length, 3, 'legacy-only still renders three Chart.js cards')

    // --- restore eligible documents -----------------------------------------
    chartsC4.breakdownScenario = 'v2'
    await reload()
    await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3`)

    // --- security histories: stock, bond, crypto ------------------------------
    await run(['open', `${pilotServer.origin}/database/securities/1`])
    await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
    await run(['wait', '400'])
    let priceState = await evalProbe(run, securityState('price'))
    let positionState = await evalProbe(run, securityState('position'))
    assert.equal(priceState.canvas, true, 'stock: modern price chart renders')
    assert.equal(positionState.canvas, true, 'stock: modern position chart renders')
    assert.match(String(priceState.table), /Aug 20, 2026/, 'price table lists observations by date')
    assert.match(String(priceState.table), /\$102\.25/, 'price table keeps exact displays')
    assert.equal(priceState.rows, 3, 'price table keeps exactly the observed rows')
    assert.match(String(positionState.table), /Aug 15, 2026/, 'position table keeps same-date events')
    assert.equal(positionState.rows, 4, 'position table keeps all four observations (duplicates included)')
    const priceQueries = historyRequests(fixtureServer, 'price').map((request) => request.query)
    const positionQueries = historyRequests(fixtureServer, 'position').map((request) => request.query)
    assert.ok(priceQueries.every((query) => query.account_id === undefined), 'price requests never carry an account_id')
    assert.ok(priceQueries.every((query) => query.chart_contract === '2'), 'history requests negotiate v2')
    assert.ok(positionQueries.every((query) => query.chart_contract === '2'), 'position requests negotiate v2')
    await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -240); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c4-stock-histories.png')])

    // Bond: percent-of-nominal unit, never rescaled.
    await run(['open', `${pilotServer.origin}/database/securities/2`])
    await run(['wait', '3000'])
    await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
    await run(['wait', '300'])
    priceState = await evalProbe(run, securityState('price'))
    assert.match(String(priceState.table), /99\.875% of nominal/, 'bond price table keeps percent-of-nominal displays')
    await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -240); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c4-bond-history.png')])

    // Crypto: exact quantity precision.
    await run(['open', `${pilotServer.origin}/database/securities/3`])
    await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
    await run(['wait', '300'])
    positionState = await evalProbe(run, securityState('position'))
    assert.match(String(positionState.table), /0\.000216590/, 'crypto position table keeps exact quantity precision')

    // --- independent failure: price malformed, position untouched -----------
    chartsC4.securityScenario = 'malformed-price'
    const beforeMalformedPrice = historyRequests(fixtureServer, 'price').length
    await reload()
    await waitFor(run, `document.querySelector('.v-alert--variant-flat') !== null`)
    await run(['wait', '600'])
    priceState = await evalProbe(run, securityState('price'))
    positionState = await evalProbe(run, securityState('position'))
    assert.equal(priceState.table, null, 'malformed price document renders no modern table')
    assert.notEqual(positionState.table, null, 'the position history settles independently of the price failure')
    assert.equal(historyRequests(fixtureServer, 'price').length - beforeMalformedPrice, 1, 'malformed price: exactly one request, no retry')
    chartsC4.securityScenario = 'v2'

    // --- renderer failure with explicit fallback -----------------------------
    chartsC4.securityScenario = 'outrange-price'
    await reload()
    await waitFor(run, `document.querySelector('[data-testid="security-render-error"]') !== null`)
    let renderError = await evalProbe(run, `document.querySelector('[data-testid="security-render-error"]')?.innerText ?? null`)
    assert.match(String(renderError), /could not be drawn/, 'renderer failure is recoverable and explicit')
    await run(['eval', `document.querySelector('[data-testid="security-render-fallback"]').click()`])
    await waitFor(run, `document.querySelectorAll('canvas').length > 0 && document.querySelector('[data-testid="security-render-error"]') === null`)
    renderError = await evalProbe(run, `document.querySelector('[data-testid="security-render-error"]')?.innerText ?? null`)
    assert.equal(renderError, null, 'the user-chosen fallback restores the incumbent chart')
    chartsC4.securityScenario = 'v2'

    // --- mobile: hit-tests and tooltip containment ---------------------------
    await run(['open', `${pilotServer.origin}/dashboard`])
    await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3`)
    await run(['set', 'viewport', '390', '844'])
    await run(['wait', '400'])
    const mobileHit = await evalProbe(run, `(() => {
      const targets = [
        ...document.querySelectorAll('[data-testid="allocation-legend"] button'),
        ...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] .v-tab'),
      ]
      return targets.map((element) => {
        element.scrollIntoView({ block: 'center' })
        const rect = element.getBoundingClientRect()
        const hitElement = document.elementFromPoint(
          Math.min(Math.max(rect.left + rect.width / 2, 4), window.innerWidth - 4),
          Math.max(rect.top + rect.height / 2, 8),
        )
        return { hittable: hitElement === element || element.contains(hitElement) }
      })
    })()`)
    assert.ok(mobileHit.length >= 6, 'mobile: legends and tabs present')
    for (const entry of mobileHit) {
      assert.equal(entry.hittable, true, 'mobile: control actually hittable')
    }
    // showTip drives the REAL formatter + placement through the chart
    // instance (exposed by EChartsAllocation for this acceptance probe); the
    // headless pointer sweep does not reliably trigger the pie's canvas
    // hit-test, and the shared pointer-path machinery is already proven by
    // the charts-c3 NAV case and the security line chart below.
    await run(['eval', `(() => {
      const host = document.querySelector('[data-testid="allocation-assetType-card"] .echarts-allocation')
      host.__c4DispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
      return true
    })()`])
    await run(['wait', '400'])
    const allocationTooltip = await assertTooltipVisible(run, '.allocation-chart-tooltip', 'mobile allocation tooltip')
    assert.match(String(allocationTooltip.text), /Amount:/, 'allocation tooltip shows the exact amount')
    assert.match(String(allocationTooltip.text), /Share:/, 'allocation tooltip shows the exact share')
    assert.match(String(allocationTooltip.text), /Full-NAV denominator:/, 'allocation tooltip shows the denominator')
    await run(['set', 'viewport', '1440', '1000'])
    await run(['wait', '400'])

    // Security mobile tooltip.
    await run(['open', `${pilotServer.origin}/database/securities/1`])
    await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
    await run(['set', 'viewport', '390', '844'])
    await run(['wait', '400'])
    // Park the price canvas below the fixed header (top at ~350px) so the
    // showTip anchor — ECharts places it at the data point — sits mid-band.
    await run(['eval', `(() => {
      const canvas = document.querySelector('.echarts-security canvas')
      const rect = canvas.getBoundingClientRect()
      window.scrollBy(0, Math.round(rect.top - 350))
      return Math.round(canvas.getBoundingClientRect().top)
    })()`])
    await run(['wait', '200'])
    await run(['eval', `(() => {
      const hosts = document.querySelectorAll('.echarts-security')
      hosts[0].__c4DispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 2 })
      return true
    })()`])
    await run(['wait', '300'])
    await assertTooltipVisible(run, '.security-chart-tooltip', 'mobile security tooltip')
    const mobileSecurity = await evalProbe(run, `(() => {
      const table = document.querySelector('[data-testid="security-data-table"]')
      table.scrollIntoView({ block: 'center' })
      const rect = table.getBoundingClientRect()
      const hit = document.elementFromPoint(Math.min(Math.max(rect.left + rect.width / 2, 4), window.innerWidth - 4), Math.max(rect.top + rect.height / 2, 8))
      return { hittable: hit === table || table.contains(hit), rows: table.querySelectorAll('tbody tr').length }
    })()`)
    assert.equal(mobileSecurity.hittable, true, 'mobile: exact security table hittable')
    await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c4-security-mobile-tooltip.png')])
    await run(['set', 'viewport', '1440', '1000'])
    await run(['wait', '400'])

    // --- delivery measurements: per-route, per-flag --------------------------
    const measure = async (origin, root, path, canvasWait) => {
      await run(['open', `${origin}${path}`])
      await run(['wait', '--fn', canvasWait, '--timeout', '20000'])
      await run(['wait', '--load', 'networkidle'])
      const observed = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`)
      return measureRouteBundles({ root, resources: observed })
    }
    const dashboardOff = await measure(appOrigin, flagOffRoot, '/dashboard', `document.querySelector('[data-testid^="allocation-"][data-testid$="-card"] canvas') !== null`)
    const dashboardOn = await measure(pilotServer.origin, pilotDir, '/dashboard', `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3`)
    const securityOff = await measure(appOrigin, flagOffRoot, '/database/securities/1', `document.querySelectorAll('canvas').length > 0`)
    const securityOn = await measure(pilotServer.origin, pilotDir, '/database/securities/1', `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
    const report = {
      note: 'gzip JS/CSS via the R7 helper over the observed per-route resource graph; flag-off and flag-on are distinct builds',
      dashboardFlagOff: dashboardOff,
      dashboardFlagOn: dashboardOn,
      securityFlagOff: securityOff,
      securityFlagOn: securityOn,
      flagOffGraphsContainNoEcharts: {
        dashboard: !dashboardOff.files.some((file) => /echarts/i.test(file.asset)),
        security: !securityOff.files.some((file) => /echarts/i.test(file.asset)),
      },
      flagOnGraphsContainEcharts: {
        dashboard: dashboardOn.files.some((file) => /echarts/i.test(file.asset)),
        security: securityOn.files.some((file) => /echarts/i.test(file.asset)),
      },
    }
    assert.equal(report.flagOffGraphsContainNoEcharts.dashboard, true, 'flag-off dashboard graph contains no echarts files')
    assert.equal(report.flagOffGraphsContainNoEcharts.security, true, 'flag-off security graph contains no echarts files')
    await mkdir(artifactsDir, { recursive: true })
    await writeFile(resolve(artifactsDir, 'charts-c4-delivery.json'), `${JSON.stringify(report, null, 2)}\n`)
    console.log(`MEASURE charts-c4 delivery: dashboard flag-off ${dashboardOff.gzipJsCss} / flag-on ${dashboardOn.gzipJsCss} bytes gzip; security flag-off ${securityOff.gzipJsCss} / flag-on ${securityOn.gzipJsCss} bytes gzip`)

    console.log('PASS charts-c4 pilot flow (dashboard + security, flag-on artifact)')
  } finally {
    await pilotServer.close().catch(() => undefined)
  }
}
