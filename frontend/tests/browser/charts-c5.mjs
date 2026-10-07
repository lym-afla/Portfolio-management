import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'
import { measureRouteBundles } from '../../scripts/measure-route-bundles.mjs'

// C5a rendered acceptance. Phase A (task 1 — lazy legacy fallback): on a
// clean all-modern v2 dashboard, NO Chart.js runtime module is loaded; the
// user-chosen NAV fallback downloads the legacy leaf lazily, renders the
// SAME accepted response with zero additional API calls, and does not touch
// the allocation family's policy or requests. Phase B (task 2 — deterministic
// release policy): rendered independence across flag artifacts — the NAV-only
// release stage, the explicit all-on candidate, the no-flags release
// candidate and the explicit all-off rollback. Later phases extend this case
// to the combined candidate acceptance and measured delivery.

const here = resolve(import.meta.dirname)
const DESIGN_ASSETS = resolve(here, '../../../docs/design/assets/charts-c5')

const NAV_PATH = '/dashboard/api/get-nav-chart-data/'
const BREAKDOWN_PATH = '/dashboard/api/get-breakdown/'

// Any Chart.js runtime module inside a loaded asset's module graph.
const CHARTJS_RUNTIME = /(node_modules\/chart\.js\/|node_modules\/vue-chartjs\/|node_modules\/chartjs-plugin-datalabels\/|node_modules\/chartjs-adapter-date-fns\/)/i
const ECHARTS_RUNTIME = /node_modules\/(echarts|vue-echarts|zrender)\//i

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 12000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const LOADED_MODULE_GRAPH = `(async () => {
  const membership = await fetch('/.vite/module-membership.json').then(response => response.json()).catch(() => ({}))
  const assets = [...new Set(performance.getEntriesByType('resource').map(entry => new URL(entry.name).pathname.slice(1)))]
  const modules = assets.flatMap((asset) => membership[asset] || [])
  return modules.join('\\n')
})()`

const DASHBOARD_MODERN_STATE = `(() => ({
  legends: [...document.querySelectorAll('[data-testid="allocation-legend"]')].length,
  allocationCanvases: [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length,
  navPilot: !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas'),
}))()`

const navRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === NAV_PATH).length

const breakdownRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === BREAKDOWN_PATH).length

async function buildC5Artifact(frontendRoot, artifactsDir, name, flags) {
  const dir = resolve(artifactsDir, name)
  const previous = { ...process.env }
  for (const [key, value] of Object.entries(flags)) {
    // A null value means the key must be genuinely ABSENT for this build —
    // the no-flags release candidate — not inherited from the environment.
    if (value === null) delete process.env[key]
    else process.env[key] = value
  }
  try {
    await build({ mode: 'browser-test', root: frontendRoot, build: { emptyOutDir: true, outDir: dir } })
  } finally {
    for (const key of Object.keys(flags)) {
      if (previous[key] === undefined) delete process.env[key]
      else process.env[key] = previous[key]
    }
  }
  return dir
}

async function openDashboardModern(run, origin) {
  await run(['open', `${origin}/dashboard`])
  await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3 && !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas')`)
}

async function openDashboardNavOnly(run, origin) {
  await run(['open', `${origin}/dashboard`])
  await waitFor(run, `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas') && [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3 && !document.querySelector('[data-testid="allocation-legend"]')`)
}

async function openDashboardLegacyAllocation(run, origin) {
  await run(['open', `${origin}/dashboard`])
  await waitFor(run, `[...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3 && !document.querySelector('[data-testid="allocation-legend"]')`)
}

async function openSecurityModern(run, origin) {
  await run(['open', `${origin}/database/securities/1`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
}

async function openSecurityLegacy(run, origin) {
  await run(['open', `${origin}/database/securities/1`])
  await waitFor(run, `document.querySelectorAll('canvas').length >= 2 && document.querySelectorAll('[data-testid="security-data-table"]').length === 0`)
}

async function loadedGraph(run) {
  await run(['wait', '--load', 'networkidle'])
  return String(await evalProbe(run, LOADED_MODULE_GRAPH))
}

// Phase A: fallback laziness on the explicit all-on artifact.
async function phaseALaziness({ candidateServer, fixtureServer, run }) {
  await openDashboardModern(run, candidateServer.origin)
  const graphBefore = await loadedGraph(run)
  assert.equal(
    CHARTJS_RUNTIME.test(graphBefore),
    false,
    'all-modern dashboard must load no Chart.js runtime module (found chart.js modules in the loaded graph)',
  )
  assert.ok(/echarts/i.test(graphBefore), 'the modern dashboard still loads the ECharts runtime')

  const navBefore = navRequestCount(fixtureServer)
  const breakdownBefore = breakdownRequestCount(fixtureServer)
  fixtureServer.charts.scenario = 'outrange'
  // A frequency change re-queries through the single owner; the unrenderable
  // document must surface the recoverable renderer error.
  await run(['eval', `(() => {
    const buttons = [...document.querySelectorAll('[data-testid="nav-chart"] button')]
    const week = buttons.find((button) => button.textContent.trim() === 'Week')
    week.click()
    return true
  })()`])
  await waitFor(run, `document.querySelector('[data-testid="chart-render-error"]') !== null`)
  assert.equal(navRequestCount(fixtureServer) - navBefore, 1, 'the failing re-query is one request')

  await run(['eval', `document.querySelector('[data-testid="chart-render-fallback"]').click()`])
  await waitFor(run, `document.querySelector('[data-testid="nav-fallback-notice"]') !== null && document.querySelector('[data-testid="nav-chart"] canvas') !== null`)
  assert.equal(navRequestCount(fixtureServer) - navBefore, 1, 'the fallback must not issue any additional API call')

  const graphAfter = await loadedGraph(run)
  assert.equal(
    CHARTJS_RUNTIME.test(graphAfter),
    true,
    'invoking the fallback must lazily download the Chart.js runtime',
  )

  const allocationLegends = await evalProbe(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length`)
  assert.equal(allocationLegends, 3, 'allocation family stays modern after the NAV fallback')
  assert.equal(breakdownRequestCount(fixtureServer) - breakdownBefore, 0, 'NAV fallback triggers no allocation refetch')
  fixtureServer.charts.scenario = 'v2'
  console.log('PASS charts-c5 laziness (modern graph chartjs-free; fallback lazy, same response, no refetch)')
}

// Phase B: rendered independence across the release-flag artifacts.
async function phaseBPolicyMatrix({ appOrigin, candidateServer, noFlagsServer, navOnlyServer, run }) {
  // NAV-only release stage: NAV modern; allocations and security incumbent.
  await openDashboardNavOnly(run, navOnlyServer.origin)
  let state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot, true, 'NAV-only artifact: the NAV pilot renders')
  assert.equal(state.legends, 0, 'NAV-only artifact: allocation stays on the incumbent bars')
  assert.equal(state.allocationCanvases, 3, 'NAV-only artifact: three incumbent allocation cards')
  let graph = await loadedGraph(run)
  assert.ok(/echarts/i.test(graph), 'NAV-only artifact: the dashboard loads the ECharts NAV runtime')
  assert.equal(CHARTJS_RUNTIME.test(graph), true, 'NAV-only artifact: incumbent allocation cards load Chart.js through the lazy legacy leaf')
  await openSecurityLegacy(run, navOnlyServer.origin)
  graph = await loadedGraph(run)
  assert.equal(ECHARTS_RUNTIME.test(graph), false, 'NAV-only artifact: security page loads no ECharts runtime')
  assert.equal(CHARTJS_RUNTIME.test(graph), true, 'NAV-only artifact: security incumbent charts are the lazily loaded Chart.js leaves')

  // Explicit all-on candidate: the same behavior under explicit flags.
  await openDashboardModern(run, candidateServer.origin)
  state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot && state.legends === 3 && state.allocationCanvases === 3, true, 'all-on candidate: three pies plus the NAV pilot')
  await openSecurityModern(run, candidateServer.origin)

  // The no-flags build IS the release candidate: built with every VITE_*
  // flag genuinely ABSENT, it must render identically to the explicit
  // all-on artifact.
  await openDashboardModern(run, noFlagsServer.origin)
  state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot && state.legends === 3 && state.allocationCanvases === 3, true, 'no-flags candidate: three pies plus the NAV pilot')
  await openSecurityModern(run, noFlagsServer.origin)

  // Explicit all-off rollback (the run-smoke base artifact configuration).
  await openDashboardLegacyAllocation(run, appOrigin)
  state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot, false, 'all-off rollback: the incumbent NAV chart renders, no pilot')
  assert.equal(state.legends, 0, 'all-off rollback: no modern allocation legends')
  assert.equal(state.allocationCanvases, 3, 'all-off rollback: three incumbent allocation cards')
  graph = await loadedGraph(run)
  assert.equal(ECHARTS_RUNTIME.test(graph), false, 'all-off rollback: dashboard loads no ECharts runtime')
  await openSecurityLegacy(run, appOrigin)
  console.log('PASS charts-c5 policy matrix (NAV-only, all-on, no-flags, all-off rendered independence)')
}

// Phase C: combined release-candidate acceptance on the no-flags artifact —
// all six views together, exact values, every ineligible/error state without
// downgrade, zoom/refresh/hold retention, security switching, mobile and
// native-zoom interaction.
async function phaseCCombinedAcceptance({ candidateServer, fixtureServer, run, cdpUrl, initScript, log, session }) {
  // --- dashboard: NAV pilot interactions on the combined page --------------
  await openDashboardModern(run, candidateServer.origin)
  await waitFor(run, `document.querySelectorAll('[data-testid="nav-echarts-pilot"] tbody tr').length > 0`)
  const navBefore = navRequestCount(fixtureServer)

  // Both independent IRR controls exist with their distinct horizons; toggling
  // one leaves the other alone and issues no request.
  const legendButtons = await evalProbe(run, `[...document.querySelectorAll('[data-series-id]')].map((button) => ({ id: button.getAttribute('data-series-id'), name: button.textContent.trim(), pressed: button.getAttribute('aria-pressed') }))`)
  assert.ok(legendButtons.some((button) => button.id === 'metric:irr_interval' && /Interval IRR \(annualized\)/.test(button.name)), 'interval IRR control present with its name')
  assert.ok(legendButtons.some((button) => button.id === 'metric:irr_inception' && /Since-inception IRR \(annualized\)/.test(button.name)), 'inception IRR control present with its name')
  await run(['eval', `(() => { const b = [...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval'); b.click(); return true })()`])
  await run(['wait', '150'])
  const hidden = await evalProbe(run, `[...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval').getAttribute('aria-pressed')`)
  assert.equal(hidden, 'false', 'interval IRR hides independently')
  assert.equal(navRequestCount(fixtureServer) - navBefore, 0, 'legend toggles issue no requests')

  // Exact-value table: comma-grouped server displays, full-NAV totals column,
  // both IRR horizons named.
  const tableText = await evalProbe(run, `document.querySelector('[data-testid="nav-echarts-pilot"] table')?.innerText ?? ''`)
  assert.match(String(tableText), /\d,\d{3}/, 'NAV table shows exact comma-grouped values')
  assert.match(String(tableText), /Portfolio NAV \(all categories\)/, 'table carries the full-NAV totals column')
  assert.match(String(tableText), /Since-inception \(to \d{4}-\d{2}-\d{2}\)|Inception to \d{4}-\d{2}-\d{2}/, 'table names the inception horizon')
  await run(['eval', `(() => { const b = [...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval'); b.click(); return true })()`])

  // Keyboard entry: focusing a table row drives the same shared inspection.
  await run(['eval', `(() => { const row = document.querySelectorAll('[data-testid="nav-echarts-pilot"] tbody tr')[1]; row.focus(); row.click(); document.querySelector('.chart-inspection').scrollIntoView({ block: 'center' }); return true })()`])
  await run(['wait', '150'])
  const inspection = await evalProbe(run, `document.querySelector('.chart-inspection')?.innerText ?? ''`)
  assert.match(String(inspection), /[A-Z][a-z]{2}-\d{2}/, 'keyboard row inspection shows the selected period')

  // View-only zoom through the native selects, then TWO distinct refreshes.
  // Review round: a frequency click alone is an INCOMPATIBLE refresh (the
  // fixture answers different period keys) and only proved that controls and
  // a canvas survived. The compatible case is now a REAL re-issued query
  // answered with the same document identity — the date-range From field
  // changes while dateTo (and therefore the C2 document context and every
  // period key) stays — and BOTH zoom bounds are compared afterwards; the
  // incompatible case separately asserts that BOTH bounds reset to the new
  // document's full range.
  const zoomState = () => evalProbe(run, `(() => {
    const selects = [...document.querySelectorAll('.chart-inspection select')]
    return {
      count: selects.length,
      start: selects[0]?.value ?? null,
      end: selects[1]?.value ?? null,
      firstKey: selects[0]?.options[0]?.value ?? null,
      lastKey: selects[1]?.options[selects[1].options.length - 1]?.value ?? null,
    }
  })()`)
  const beforeZoom = await zoomState()
  assert.equal(beforeZoom.count, 2, 'native start/end zoom selects present')
  await run(['eval', `(() => {
    const select = document.querySelectorAll('.chart-inspection select')[0]
    select.value = select.options[1]?.value ?? select.value
    select.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`])
  await run(['wait', '200'])
  const zoomed = await zoomState()
  assert.notEqual(zoomed.start, beforeZoom.start, 'zoom start moved through the native control')

  // COMPATIBLE refresh: the date-range From change re-issues the query; the
  // fixture answers the SAME document (dateTo and every period key stay), so
  // the zoom window must survive with both bounds intact.
  const compatibleBefore = navRequestCount(fixtureServer)
  await run(['eval', `(() => {
    // The date-range activator is the only svg-iconed button in the NAV
    // card (the app renders @mdi/js SVG icons, not mdi-* font classes);
    // the frequency buttons are text-only.
    const activator = [...document.querySelectorAll('[data-testid="nav-chart"] button')].find((button) => button.querySelector('svg'))
    if (!activator) throw new Error('date-range activator missing')
    activator.click()
    return true
  })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active input[type="date"]') !== null`)
  await run(['eval', `(() => {
    const input = document.querySelector('.v-overlay--active input[type="date"]')
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    setter.call(input, '2026-02-01')
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
    return input.value
  })()`])
  await run(['eval', `(() => {
    const apply = [...document.querySelectorAll('.v-overlay--active button')].find((button) => button.textContent.trim() === 'Apply')
    apply.click()
    return true
  })()`])
  await waitFor(run, `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas') && document.querySelector('[data-testid="nav-error"]') === null`)
  await run(['wait', '600'])
  assert.equal(navRequestCount(fixtureServer) - compatibleBefore, 1, 'the compatible date re-query is one request')
  const afterCompatible = await zoomState()
  assert.equal(afterCompatible.start, zoomed.start, 'compatible refresh retains the zoom START bound')
  assert.equal(afterCompatible.end, zoomed.end, 'compatible refresh retains the zoom END bound')

  // INCOMPATIBLE refresh: the fixture switches to a same-shaped document
  // whose period keys all differ (`altkeys`), so nothing from the previous
  // viewport can map — BOTH bounds must reset to the new document's full
  // range (never leak), with exactly one request and no error. A frequency
  // button carries no aria-pressed (Vuetify toggle); the refresh is verified
  // by the re-rendered pilot plus the request count.
  const incompatibleBefore = navRequestCount(fixtureServer)
  fixtureServer.charts.scenario = 'altkeys'
  await run(['eval', `(() => {
    const buttons = [...document.querySelectorAll('[data-testid="nav-chart"] button')]
    const day = buttons.find((button) => button.textContent.trim() === 'Day')
    day.click()
    return true
  })()`])
  await waitFor(run, `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas') && document.querySelector('[data-testid="nav-error"]') === null`)
  await run(['wait', '600'])
  assert.equal(navRequestCount(fixtureServer) - incompatibleBefore, 1, 'the incompatible re-query is one request')
  const afterIncompatible = await zoomState()
  assert.equal(afterIncompatible.count, 2, 'zoom controls survive the incompatible refresh')
  assert.equal(afterIncompatible.start, afterIncompatible.firstKey, 'incompatible refresh resets the zoom START bound to the full range')
  assert.equal(afterIncompatible.end, afterIncompatible.lastKey, 'incompatible refresh resets the zoom END bound to the full range')
  assert.equal(await evalProbe(run, `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas')`), true, 'pilot re-renders after the refresh')
  fixtureServer.charts.scenario = 'v2'

  // Parked responses: a period change held at the fixture leaves the previous
  // chart visibly loading, never looking current with new labels.
  const parkBefore = navRequestCount(fixtureServer)
  fixtureServer.charts.scenario = 'hold'
  await run(['eval', `(() => {
    const buttons = [...document.querySelectorAll('[data-testid="nav-chart"] button')]
    const week = buttons.find((button) => button.textContent.trim() === 'Week')
    week.click()
    return true
  })()`])
  await run(['wait', '800'])
  assert.equal(navRequestCount(fixtureServer) - parkBefore, 1, 'the parked request was issued once')
  const parkedState = await evalProbe(run, `(() => ({
    canvas: !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas'),
    error: !!document.querySelector('[data-testid="nav-error"]'),
  }))()`)
  assert.equal(parkedState.canvas, true, 'the previous chart stays rendered while the response is parked')
  assert.equal(parkedState.error, false, 'a parked response is not an error')
  fixtureServer.charts.scenario = 'v2'
  await run(['eval', `(() => {
    const buttons = [...document.querySelectorAll('[data-testid="nav-chart"] button')]
    const month = buttons.find((button) => button.textContent.trim() === 'Month')
    month.click()
    return true
  })()`])
  await waitFor(run, `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas') && document.querySelector('[data-testid="nav-error"]') === null`)
  await run(['wait', '400'])
  assert.equal(navRequestCount(fixtureServer) - parkBefore, 2, 'the replacement query lands after the parked one')

  // --- allocation states on the combined page ------------------------------
  const chartsC4 = fixtureServer.chartsC4
  chartsC4.breakdownScenario = 'signed'
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="allocation-ineligible"]') !== null`)
  const signedReason = await evalProbe(run, `document.querySelector('[data-testid="allocation-ineligible"]')?.innerText ?? ''`)
  assert.match(String(signedReason), /negative/, 'the signed state shows the certified misleading-pie reason')
  await run(['eval', `(() => {
    const tabs = [...document.querySelector('[data-testid="allocation-assetType-card"]').querySelectorAll('.v-tab')]
    tabs.find((tab) => tab.textContent.trim() === 'Table').click()
    return true
  })()`])
  await run(['wait', '200'])
  const signedTable = await evalProbe(run, `document.querySelector('[data-testid="allocation-assetType-card"] [data-testid="allocation-data-table"]')?.innerText ?? ''`)
  assert.match(String(signedTable), /\(\$25\.00\)/, 'the signed row keeps its exact parenthesized negative')
  assert.match(String(signedTable), /-25\.0%/, 'the signed share stays verbatim')
  assert.match(String(signedTable), /(\$|USD )?100\.00/, 'the full-NAV denominator is unchanged')
  await run(['eval', `(() => { document.querySelector('[data-testid="allocation-assetType-card"]').scrollIntoView({ block: 'center' }); return true })()`])
  await run(['wait', '150'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'c5-ineligible-table.png')])

  // Malformed v2: section error, exactly one request, no retry, no downgrade.
  chartsC4.breakdownScenario = 'malformed'
  const malformedBefore = breakdownRequestCount(fixtureServer)
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="allocation-assetType-error"]') !== null`)
  await run(['wait', '700'])
  assert.equal(breakdownRequestCount(fixtureServer) - malformedBefore, 1, 'malformed v2: exactly one request, no retry loop')

  // Legacy-only: honest notice plus the incumbent bars from the lazy leaf.
  chartsC4.breakdownScenario = 'legacy'
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="allocation-capability-notice"]') !== null && [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3`)
  const legacyNotice = await evalProbe(run, `document.querySelector('[data-testid="allocation-capability-notice"]')?.innerText ?? ''`)
  assert.match(String(legacyNotice), /legacy response/, 'legacy-only shows the honest capability notice')
  chartsC4.breakdownScenario = 'v2'

  // --- security histories on the candidate ---------------------------------
  await openSecurityModern(run, candidateServer.origin)
  await run(['wait', '400'])
  const stockState = await evalProbe(run, `(() => {
    const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]
    return { tables: tables.length, texts: tables.map((t) => t.innerText) }
  })()`)
  assert.equal(stockState.tables, 2, 'stock: both modern histories render with exact tables')
  assert.match(String(stockState.texts[0]), /\$102\.25/, 'price table keeps exact dollar displays')
  assert.match(String(stockState.texts[0]), /carried forward|Aug 20, 2026/, 'price table lists observations by date')
  assert.match(String(stockState.texts[1]), /8\.000000000/, 'position table keeps exact quantities')

  // Renderer failure with explicit recovery, driven through the real
  // instance hook: retry first (fails again), then the user-chosen fallback.
  chartsC4.securityScenario = 'outrange-price'
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="security-render-error"]') !== null`)
  await run(['eval', `document.querySelector('[data-testid="security-render-retry"]')?.click(); true`])
  await run(['wait', '400'])
  assert.ok(await evalProbe(run, `document.querySelector('[data-testid="security-render-error"]') !== null`), 'a retry of a deterministically broken renderer keeps the error visible')
  await run(['eval', `document.querySelector('[data-testid="security-render-fallback"]').click()`])
  await waitFor(run, `document.querySelectorAll('canvas').length >= 2 && document.querySelector('[data-testid="security-render-error"]') === null`)
  chartsC4.securityScenario = 'v2'

  // --- security zoom: switch after zoom, no cross-context leakage -----------
  await openSecurityModern(run, candidateServer.origin)
  await waitFor(run, `document.querySelectorAll('.echarts-security canvas').length >= 1`)
  await run(['wait', '400'])
  await run(['eval', `(() => {
    const host = document.querySelector('.echarts-security')
    host.__c4DispatchAction({ type: 'dataZoom', start: 40, end: 70 })
    return true
  })()`])
  await run(['wait', '300'])
  // Switching the security replaces the document: the view-only zoom resets
  // with the new context and the bond renders its full percent-of-nominal
  // range without carrying the stock zoom or crashing.
  await run(['open', `${candidateServer.origin}/database/securities/2`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
  await run(['wait', '300'])
  const bondState = await evalProbe(run, `(() => {
    const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]
    return { tables: tables.length, text: tables[0]?.innerText ?? '' }
  })()`)
  assert.match(String(bondState.text), /99\.875% of nominal/, 'bond price table keeps percent-of-nominal displays')
  assert.equal(bondState.tables, 2, 'bond: both histories render')
  // The rendered bond chart is fully the new context: its first tooltip is
  // the bond's first observation, not a leaked stock point.
  await run(['eval', `(() => {
    const host = document.querySelector('.echarts-security')
    host.__c4DispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
    return true
  })()`])
  await run(['wait', '300'])
  const bondTip = await evalProbe(run, `(() => {
    const tooltip = [...document.querySelectorAll('.security-chart-tooltip')].find((div) => (div.innerText || '').trim().length > 0)
    return tooltip ? tooltip.innerText : null
  })()`)
  assert.match(String(bondTip), /99\.125% of nominal/, 'the bond chart shows bond data — no cross-security leakage')
  const bondErrors = await runAgentBrowser({ args: ['errors'], context: 'charts c5 bond errors', initScript, log, session })
  assert.deepEqual(bondErrors.errors, [], 'switching securities after zoom leaves no page errors')
  await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
  await run(['wait', '150'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'c5-bond-history.png')])

  await run(['open', `${candidateServer.origin}/database/securities/3`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
  const cryptoState = await evalProbe(run, `[...document.querySelectorAll('[data-testid="security-data-table"]')].map((t) => t.innerText).join('\\n')`)
  assert.match(String(cryptoState), /0\.000216590/, 'crypto position table keeps exact quantity precision')
  await run(['eval', `(() => { document.querySelector('#security-position-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
  await run(['wait', '150'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'c5-crypto-history.png')])

  // --- mobile: combined page containment, tooltip, restore ------------------
  await openDashboardModern(run, candidateServer.origin)
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '600'])
  const mobileHit = await evalProbe(run, `(() => {
    const targets = [
      ...document.querySelectorAll('[data-series-id]'),
      ...document.querySelectorAll('[data-testid="allocation-legend"] button'),
      ...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] .v-tab'),
      ...document.querySelectorAll('.chart-inspection select, .chart-inspection__reset'),
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
  assert.ok(mobileHit.length >= 8, 'mobile: combined-page controls present')
  for (const entry of mobileHit) {
    assert.equal(entry.hittable, true, 'mobile: control actually hittable')
  }

  // NAV mobile tooltip via the C3 capture tooling: a real two-step pointer
  // sweep over CDP with full-visibility verification and a viewport-only
  // capture at the hover instant (synthetic mousemove events do not
  // reliably drive ECharts' canvas hit-test).
  await run(['eval', `(() => { window.__c3CaptureTab = true; return true })()`])
  const mobileCapture = await new Promise((resolveSpawn) => {
    const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-tooltip-capture.mjs'), String(cdpUrl), candidateServer.origin, resolve(DESIGN_ASSETS, 'c5-nav-mobile-tooltip.png'), '0.5'], { stdio: 'pipe' })
    let out = ''
    child.stdout.on('data', (chunk) => { out += chunk })
    child.stderr.on('data', (chunk) => { out += chunk })
    child.on('error', (error) => resolveSpawn({ code: -1, out: String(error) }))
    child.on('close', (code) => resolveSpawn({ code, out }))
  })
  assert.equal(mobileCapture.code, 0, `mobile tooltip must be captured fully visible (${mobileCapture.out.slice(-600)})`)

  // Desktop restore, then native 200% zoom (DPR verified) and reset.
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '500'])
  await run(['eval', `(() => { window.__c3CaptureTab = true; return true })()`])
  await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
  await run(['wait', '150'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'c5-dashboard-modern.png')])
  const zoomScript = await new Promise((resolveSpawn, rejectSpawn) => {
    const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), candidateServer.origin, '200'], { stdio: 'pipe' })
    let out = ''
    child.stdout.on('data', (chunk) => { out += chunk })
    child.stderr.on('data', (chunk) => { out += chunk })
    child.on('error', rejectSpawn)
    child.on('close', (code) => resolveSpawn({ code, out }))
  })
  assert.equal(zoomScript.code, 0, `native 200% zoom must be dpr-verified (${zoomScript.out.trim()})`)
  const zoomedProbe = await evalProbe(run, `(() => ({
    pilot: !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas'),
    legends: document.querySelectorAll('[data-testid="allocation-legend"]').length,
    dpr: window.devicePixelRatio,
  }))()`)
  assert.equal(zoomedProbe.pilot, true, 'native 200%: NAV pilot still renders')
  assert.equal(zoomedProbe.legends, 3, 'native 200%: allocation legends still render')
  await run(['screenshot', resolve(DESIGN_ASSETS, 'c5-native-zoom.png')])
  await new Promise((resolveSpawn) => {
    const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), candidateServer.origin, '100'], { stdio: 'ignore' })
    child.on('error', () => {})
    child.on('close', () => resolveSpawn())
  })
  const dprReset = await evalProbe(run, `window.devicePixelRatio`)
  assert.equal(dprReset, 1, 'native zoom reset restores DPR 1')
  console.log('PASS charts-c5 combined acceptance (six views, states, zoom/refresh, mobile, native zoom)')
}

// Phase D: cold-route delivery measurements across the flag artifacts plus
// capture verification/registration.
async function phaseDDelivery({ appOrigin, flagOffRoot, candidateServer, candidateDir, navOnlyServer, navOnlyDir, fixtureServer, run }) {
  const measure = async (origin, root, path, canvasWait) => {
    await run(['open', `${origin}${path}`])
    await run(['wait', '--fn', canvasWait, '--timeout', '20000'])
    await run(['wait', '--load', 'networkidle'])
    const observed = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`)
    return measureRouteBundles({ root, resources: observed })
  }
  const noGraph = `document.body.innerText.length > 0`
  const dashboards = {
    modernDefault: await measure(candidateServer.origin, candidateDir, '/dashboard', `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3 && !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas')`),
    navOnly: await measure(navOnlyServer.origin, navOnlyDir, '/dashboard', `!!document.querySelector('[data-testid="nav-echarts-pilot"] canvas') && [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3`),
    allOffRollback: await measure(appOrigin, flagOffRoot, '/dashboard', `[...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3 && !document.querySelector('[data-testid="allocation-legend"]')`),
  }
  // Fallback activated: the SAME candidate build after the user-chosen NAV
  // fallback lazily downloads the legacy runtime.
  await run(['open', `${candidateServer.origin}/dashboard`])
  await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3`)
  fixtureServer.charts.scenario = 'outrange'
  await run(['eval', `(() => {
    const buttons = [...document.querySelectorAll('[data-testid="nav-chart"] button')]
    const week = buttons.find((button) => button.textContent.trim() === 'Week')
    week.click()
    return true
  })()`])
  await waitFor(run, `document.querySelector('[data-testid="chart-render-error"]') !== null`)
  await run(['eval', `document.querySelector('[data-testid="chart-render-fallback"]').click()`])
  await waitFor(run, `document.querySelector('[data-testid="nav-fallback-notice"]') !== null && document.querySelector('[data-testid="nav-chart"] canvas') !== null`)
  fixtureServer.charts.scenario = 'v2'
  await run(['wait', '--load', 'networkidle'])
  const fallbackObserved = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`)
  const fallbackActivated = await measureRouteBundles({ root: candidateDir, resources: fallbackObserved })

  const loginModern = await measure(candidateServer.origin, candidateDir, '/login', noGraph)
  const profileModern = await measure(candidateServer.origin, candidateDir, '/profile', `document.body.innerText.length > 100`)
  const transactionsModern = await measure(candidateServer.origin, candidateDir, '/transactions', `document.body.innerText.length > 100`)
  const securityModern = await measure(candidateServer.origin, candidateDir, '/database/securities/1', `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)

  for (const [name, graph] of [['login', loginModern], ['profile', profileModern], ['transactions', transactionsModern]]) {
    const modules = graph.modules.join('\\n')
    assert.equal(CHARTJS_RUNTIME.test(modules), false, `${name}: no Chart.js runtime module on the cold route`)
    assert.equal(ECHARTS_RUNTIME.test(modules), false, `${name}: no ECharts runtime module on the cold route`)
  }

  const dashboardBudgetBytes = 535_000
  const report = {
    note: 'gzip+raw JS/CSS via the R7 helper over the observed per-route cold resource graph. Charts-c5: the no-flags artifact IS the modern default; NAV-only and all-off rollback are distinct builds; fallback-activated is the candidate build after the user-chosen legacy fallback. Loopback timings are not production latency evidence; fonts are reported separately (system stack expects zero).',
    budget: { dashboardModernTargetGzip: dashboardBudgetBytes, withinTarget: null, historicalPreChartTargetGzip: 401_000 },
    dashboard: {
      modernDefault: { gzip: dashboards.modernDefault.gzipJsCss, raw: dashboards.modernDefault.files.reduce((t, f) => t + f.bytes, 0), assets: dashboards.modernDefault.assets.length, emittedManifestEntries: dashboards.modernDefault.manifestEntries },
      navOnly: { gzip: dashboards.navOnly.gzipJsCss, raw: dashboards.navOnly.files.reduce((t, f) => t + f.bytes, 0) },
      allOffRollback: { gzip: dashboards.allOffRollback.gzipJsCss, raw: dashboards.allOffRollback.files.reduce((t, f) => t + f.bytes, 0) },
      fallbackActivated: { gzip: fallbackActivated.gzipJsCss, raw: fallbackActivated.files.reduce((t, f) => t + f.bytes, 0), chartjsInGraph: CHARTJS_RUNTIME.test(fallbackActivated.modules.join('\\n')) },
    },
    candidateColdRoutes: {
      login: { gzip: loginModern.gzipJsCss, raw: loginModern.files.reduce((t, f) => t + f.bytes, 0) },
      profile: { gzip: profileModern.gzipJsCss, raw: profileModern.files.reduce((t, f) => t + f.bytes, 0) },
      transactions: { gzip: transactionsModern.gzipJsCss, raw: transactionsModern.files.reduce((t, f) => t + f.bytes, 0) },
      securityDetail: { gzip: securityModern.gzipJsCss, raw: securityModern.files.reduce((t, f) => t + f.bytes, 0) },
    },
    fonts: {
      dashboardModernFontAssets: dashboards.modernDefault.assets.filter((asset) => /\.woff2?$/i.test(asset)),
      note: 'system font stack; any non-zero font asset here is a regression signal',
    },
    perRouteGraphs: {
      dashboardModern: dashboards.modernDefault.files.map((file) => ({ asset: file.asset, gzip: file.gzipBytes })),
      dashboardFallback: fallbackActivated.files.filter((file) => /chart/i.test(file.asset)).map((file) => ({ asset: file.asset, gzip: file.gzipBytes })),
    },
  }
  report.budget.withinTarget = dashboards.modernDefault.gzipJsCss <= dashboardBudgetBytes
  await mkdir(resolve(here, 'artifacts'), { recursive: true })
  await writeFile(resolve(here, 'artifacts/charts-c5-delivery.json'), `${JSON.stringify(report, null, 2)}\n`)
  console.log(`MEASURE charts-c5 delivery: dashboard modern ${dashboards.modernDefault.gzipJsCss} (target <= ${dashboardBudgetBytes}), NAV-only ${dashboards.navOnly.gzipJsCss}, all-off ${dashboards.allOffRollback.gzipJsCss}, fallback-activated ${fallbackActivated.gzipJsCss} bytes gzip; login ${loginModern.gzipJsCss}, profile ${profileModern.gzipJsCss}, transactions ${transactionsModern.gzipJsCss}, security ${securityModern.gzipJsCss}`)
  assert.equal(report.budget.withinTarget, true, `all-modern dashboard ${dashboards.modernDefault.gzipJsCss} gzip bytes exceeds the saved ~535 kB cutover target — record the miss and keep readiness pending`)
  return report
}

// Capture registration: SHA-256 + pixel dimensions for every c5 evidence
// image, so reviewers can verify the artifacts independently.
async function registerCaptures() {
  const { readFile } = await import('node:fs/promises')
  const { readdir } = await import('node:fs/promises')
  const entries = await readdir(DESIGN_ASSETS)
  const captures = []
  for (const entry of entries.filter((name) => name.endsWith('.png'))) {
    const bytes = await readFile(resolve(DESIGN_ASSETS, entry))
    // PNG dimensions: bytes 16..24 (big-endian width/height of IHDR).
    const width = bytes.readUInt32BE(16)
    const height = bytes.readUInt32BE(20)
    captures.push({ file: entry, sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length, width, height })
  }
  await writeFile(resolve(here, 'artifacts/charts-c5-captures.json'), `${JSON.stringify({ captures }, null, 2)}\n`)
  assert.ok(captures.length >= 6, `expected the full capture set, got ${captures.length}`)
  console.log(`MEASURE charts-c5 captures: ${captures.map((capture) => `${capture.file} ${capture.width}x${capture.height}`).join(', ')}`)
}

export async function runChartsC5Flow({
  appOrigin,
  flagOffRoot,
  frontendRoot,
  fixtureServer,
  log,
  registerSession,
  artifactsDir,
}) {
  const candidateDir = await buildC5Artifact(frontendRoot, artifactsDir, 'app-c5-candidate', {
    VITE_NAV_ECHARTS_ENABLED: 'true',
    VITE_ALLOCATION_ECHARTS_ENABLED: 'true',
    VITE_SECURITY_ECHARTS_ENABLED: 'true',
  })
  const navOnlyDir = await buildC5Artifact(frontendRoot, artifactsDir, 'app-c5-navonly', {
    VITE_NAV_ECHARTS_ENABLED: 'true',
    VITE_ALLOCATION_ECHARTS_ENABLED: 'false',
    VITE_SECURITY_ECHARTS_ENABLED: 'false',
  })
  // The no-flags artifact is the ACTUAL release candidate: built with every
  // VITE_* flag genuinely absent so the reviewed default-on policy applies.
  // Review round: this used to reuse the explicit all-on artifact, which
  // never exercised the missing-flag behavior.
  const noFlagsDir = await buildC5Artifact(frontendRoot, artifactsDir, 'app-c5-noflags', {
    VITE_NAV_ECHARTS_ENABLED: null,
    VITE_ALLOCATION_ECHARTS_ENABLED: null,
    VITE_SECURITY_ECHARTS_ENABLED: null,
  })
  const candidateServer = await startBuiltAppServer(candidateDir)
  const noFlagsServer = await startBuiltAppServer(noFlagsDir)
  const navOnlyServer = await startBuiltAppServer(navOnlyDir)
  const session = `c5-candidate-${process.pid}`
  registerSession(session)
  const initScript = resolve(frontendRoot, 'tests/browser/auth-init.js')
  const run = (args) => runAgentBrowser({ args, context: 'charts c5 candidate', initScript, log, session })

  try {
    await phaseALaziness({ candidateServer, fixtureServer, run })
    await phaseBPolicyMatrix({ appOrigin, candidateServer, noFlagsServer, navOnlyServer, run })

    // Phases C and D run against the NO-FLAGS candidate (the shipped
    // default); the CDP url drives the native-zoom and tooltip capture
    // scripts.
    const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: 'charts c5 cdp', initScript, log, session })
    const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
    await mkdir(DESIGN_ASSETS, { recursive: true })
    await phaseCCombinedAcceptance({ candidateServer: noFlagsServer, fixtureServer, run, cdpUrl, initScript, log, session })
    await phaseDDelivery({ appOrigin, flagOffRoot, candidateServer: noFlagsServer, candidateDir: noFlagsDir, navOnlyServer, navOnlyDir, fixtureServer, run })
    await registerCaptures()
  } finally {
    await candidateServer.close().catch(() => undefined)
    await noFlagsServer.close().catch(() => undefined)
    await navOnlyServer.close().catch(() => undefined)
  }
}
