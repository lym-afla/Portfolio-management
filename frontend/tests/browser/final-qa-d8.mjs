import assert from 'node:assert/strict'
import { appendFile, mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'

import { build } from 'vite'

import { startFixtureServer } from './fixture-server.mjs'
import { startBuiltAppServer } from './serve-app.mjs'
import { cleanupBrowserHarness, runBrowserHarnessLifecycle } from './lifecycle.mjs'
import { runAgentBrowser } from './protocol.mjs'
import { runRoute } from './route-probe.mjs'
import { routes, viewports } from './routes.mjs'
import { assertDialogDeliveryFlow, dialogRoutes } from './dialogs.mjs'
import { assertD4TablesFlow, assertD4TransactionsFlow, assertD4ViewportChecks } from './d4.mjs'
import { assertSettingsAccountFlow } from './settings-account.mjs'
import { assertImportsD6Flow } from './imports-d6.mjs'
import { assertBrokersSecurityD7Flow } from './brokers-security-d7.mjs'
import { assertMobilePageControlsFlow } from './d5.mjs'
import { measureRouteBundles } from '../../scripts/measure-route-bundles.mjs'
import { CHARTJS_RUNTIME, ECHARTS_RUNTIME, LOADED_MODULE_GRAPH } from './charts-c5.mjs'
import {
  applyFixtureMismatchFailures,
  collectFixtureMismatches,
  hashArtifact,
  scanFlagEnvFiles,
  withFlagEnvironment,
} from './artifact-flags.mjs'

// D8 integrated default-on frontend QA (final QA before any C5b decision).
//
// This case is the DEFAULT-ON acceptance matrix. It builds its own artifacts:
//   - app-d8-default-on: every VITE_*_ECHARTS_ENABLED key genuinely ABSENT
//     (the shipped release candidate — the reviewed default-on policy).
//   - app-d8-rollback: every key explicitly 'false' (the rollback artifact).
// The existing un-flagged run-smoke base matrix (built all-false) remains the
// full rollback route matrix and is unchanged. Result lines here are prefixed
// D8-DEFAULT-ON / D8-ROLLBACK so the two matrices can never be confused.

// Build one flag configuration into outDir with the environment saved and
// restored around the build (the build itself fails loudly on error).
export async function buildFlagArtifact(frontendRoot, outDir, flags) {
  return withFlagEnvironment(flags, () =>
    build({
      mode: 'browser-test',
      root: frontendRoot,
      build: { emptyOutDir: true, outDir },
    }))
}

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 12000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const DASHBOARD_MODERN_STATE = `(() => ({
  legends: [...document.querySelectorAll('[data-testid="allocation-legend"]')].length,
  allocationCanvases: [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length,
  navPilot: !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas'),
}))()`

const navRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === '/dashboard/api/get-nav-chart-data/').length
const breakdownRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === '/dashboard/api/get-breakdown/').length

const D8_ASSETS = (frontendRoot) => resolve(frontendRoot, '../docs/design/assets/frontend-final-qa')

// Representative captures for the default-on route matrix. Keys are
// `${viewport.name} ${route.path}`; every other matrix row runs assert-only.
const MATRIX_CAPTURES = {
  'desktop /dashboard': 'd8-dashboard-desktop.png',
  'desktop /open-positions': 'd8-open-positions-desktop.png',
  'desktop /closed-positions': 'd8-closed-positions-desktop.png',
  'desktop /transactions': 'd8-transactions-desktop.png',
  'desktop /summary': 'd8-summary-desktop.png',
  'desktop /database/brokers': 'd8-brokers-desktop.png',
  'desktop /database/securities/1': 'd8-security-detail-desktop.png',
  'desktop /profile/settings': 'd8-profile-settings-desktop.png',
  'tablet /dashboard': 'd8-dashboard-tablet.png',
  'tablet-portrait /dashboard': 'd8-dashboard-tablet-portrait.png',
  'mobile /dashboard': 'd8-dashboard-mobile.png',
  'mobile /transactions': 'd8-transactions-mobile.png',
  'mobile /database/fx': 'd8-fx-mobile.png',
  'zoom-200 /transactions': 'd8-transactions-css-zoom200.png',
}

// Long-name pass captures (non-chart routes only; the longAccount fixture
// variant's committed selection deliberately mismatches the C2/C4 chart
// envelope contexts, so chartful routes would legacy-fallback for fixture
// reasons and are not captured here).
const LONGNAME_CAPTURES = {
  'desktop /open-positions': 'd8-open-positions-longname-desktop.png',
  'desktop /transactions': 'd8-transactions-longname-desktop.png',
  'desktop /summary': 'd8-summary-longname-desktop.png',
  'desktop /database/accounts': 'd8-accounts-longname-desktop.png',
  'mobile /transactions': 'd8-transactions-longname-mobile.png',
}

// Real keyboard dialog contract on the default-on artifact: seed focus on
// the route's dialog-opening action (where a keyboard user lands after
// tabbing), activate with a real Enter key press, assert focus moved into
// the open dialog (useDialogFormFocus focuses the first eligible control),
// close with a real Escape, and assert focus returned to the same invoker.
const D8_DIALOG_INVOKERS = {
  '/transactions': 'Add transaction',
  '/database/accounts': 'Add Account',
  '/database/brokers': 'Add Broker',
  '/database/securities': 'Add Security',
  '/database/prices': 'Add Price Entry',
  '/database/fx': 'Add FX Rate',
  '/dashboard': 'Update Account Performance',
}

async function assertD8DialogKeyboardFlow({ run, route }) {
  const invokerLabel = D8_DIALOG_INVOKERS[route]
  assert.ok(invokerLabel, `dialog keyboard flow: no invoker mapped for ${route}`)
  const seed = await evalProbe(run, `(() => {
    const invoker = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '${invokerLabel}' && !b.disabled)
    if (!invoker) return { found: false }
    invoker.scrollIntoView({ block: 'center' })
    invoker.focus()
    return { found: true, focused: document.activeElement === invoker }
  })()`)
  assert.equal(seed.found, true, `dialog keyboard: invoker '${invokerLabel}' rendered on ${route}`)
  assert.equal(seed.focused, true, `dialog keyboard: invoker '${invokerLabel}' holds focus before activation`)
  await run(['press', 'Enter'])
  await waitFor(run, `document.querySelector('.v-dialog.v-overlay--active .v-card') !== null`)
  const focusInDialog = await evalProbe(run, `(() => { const overlay = document.querySelector('.v-dialog.v-overlay--active'); return { open: !!overlay, focusInside: !!overlay && overlay.contains(document.activeElement), tag: document.activeElement ? document.activeElement.tagName : null } })()`)
  assert.equal(focusInDialog.open, true, `dialog keyboard: dialog open after Enter (${invokerLabel})`)
  assert.equal(focusInDialog.focusInside, true, `dialog keyboard: focus entered the dialog (activeElement is ${focusInDialog.tag})`)
  await run(['press', 'Escape'])
  await waitFor(run, `document.querySelector('.v-dialog.v-overlay--active') === null`)
  const focusAfter = await evalProbe(run, `(() => { const invoker = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '${invokerLabel}'); return { backOnInvoker: document.activeElement === invoker, active: document.activeElement ? document.activeElement.tagName : null } })()`)
  assert.equal(focusAfter.backOnInvoker, true, `dialog keyboard: focus returned to the invoker after Escape (${invokerLabel})`)
}

// The D8 viewport set: the four production viewports plus 768x1024
// (tablet-portrait), which the broker-manager flows already target, and the
// CSS zoom-200 viewport (distinct from the native-zoom flow, which is driven
// through CDP with a real DPR change later in this case).
const D8_VIEWPORTS = [
  ...viewports,
  { name: 'tablet-portrait', width: 768, height: 1024, zoom: 1 },
]

const registerPngCaptures = async (assetsDir) => {
  const entries = await readdir(assetsDir)
  const captures = []
  for (const entry of entries.filter((name) => name.endsWith('.png')).sort()) {
    const bytes = await readFile(resolve(assetsDir, entry))
    const width = bytes.readUInt32BE(16)
    const height = bytes.readUInt32BE(20)
    captures.push({ file: entry, sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length, width, height })
  }
  return captures
}

// ---------------------------------------------------------------------------
// Phase C2: integrated chart acceptance on the default-on artifact. Same
// fixture scenario machinery as the C5a case, but every capture lands in the
// D8 assets directory and every result is labeled D8-DEFAULT-ON.
// ---------------------------------------------------------------------------
async function assertD8ChartAcceptance({ appOrigin, fixtureServer, frontendRoot, run, cdpUrl, initScript, log, session, captures }) {
  const shoot = async (name) => {
    await run(['screenshot', resolve(D8_ASSETS(frontendRoot), name)])
    captures.push(name)
  }

  // --- dashboard: NAV pilot with both IRR horizons --------------------------
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.querySelectorAll('[data-testid="nav-echarts-pilot"] tbody tr').length > 0`)
  const navBefore = navRequestCount(fixtureServer)

  const legendButtons = await evalProbe(run, `[...document.querySelectorAll('[data-series-id]')].map((button) => ({ id: button.getAttribute('data-series-id'), name: button.textContent.trim(), pressed: button.getAttribute('aria-pressed') }))`)
  assert.ok(legendButtons.some((button) => button.id === 'metric:irr_interval' && /Interval IRR \(annualized\)/.test(button.name)), 'interval IRR control present with its name')
  assert.ok(legendButtons.some((button) => button.id === 'metric:irr_inception' && /Since-inception IRR \(annualized\)/.test(button.name)), 'inception IRR control present with its name')
  await run(['eval', `(() => { const b = [...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval'); b.click(); return true })()`])
  await run(['wait', '150'])
  const hidden = await evalProbe(run, `[...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval').getAttribute('aria-pressed')`)
  assert.equal(hidden, 'false', 'interval IRR hides independently')
  assert.equal(navRequestCount(fixtureServer) - navBefore, 0, 'legend toggles issue no requests')

  const tableText = await evalProbe(run, `document.querySelector('[data-testid="nav-echarts-pilot"] table')?.innerText ?? ''`)
  assert.match(String(tableText), /\d,\d{3}/, 'NAV table shows exact comma-grouped values')
  assert.match(String(tableText), /Portfolio NAV \(all categories\)/, 'table carries the full-NAV totals column')
  assert.match(String(tableText), /Since-inception \(to \d{4}-\d{2}-\d{2}\)|Inception to \d{4}-\d{2}-\d{2}/, 'table names the inception horizon')
  await run(['eval', `(() => { const b = [...document.querySelectorAll('[data-series-id]')].find((x) => x.getAttribute('data-series-id') === 'metric:irr_interval'); b.click(); return true })()`])

  // REAL keyboard activation: the exact-values table region is a tab stop;
  // its rows are tab stops with Enter/Space handlers (ChartDataTable.vue).
  // Seed focus on the region (where a keyboard user lands), then drive real
  // Tab + Enter key events and assert the focused element and the inspected
  // period — no synthetic focus()/click() on the row.
  await run(['eval', `(() => { const region = document.querySelector('[data-testid="nav-echarts-pilot"] .chart-table'); if (!region) throw new Error('chart table region missing'); region.scrollIntoView({ block: 'center' }); region.focus(); return document.activeElement === region })()`])
  await run(['press', 'Tab'])
  const rowFocus = await evalProbe(run, `(() => { const el = document.activeElement; return { isRow: !!el && el.tagName === 'TR' && !!el.closest('[data-testid="nav-echarts-pilot"]'), period: el && el.tagName === 'TR' ? (el.querySelector('.chart-table__period')?.childNodes[0]?.textContent ?? '').trim() : null } })()`)
  assert.equal(rowFocus.isRow, true, 'Tab moves from the table region into its first row')
  await run(['press', 'Enter'])
  await run(['wait', '300'])
  const inspection = await evalProbe(run, `document.querySelector('.chart-inspection')?.innerText ?? ''`)
  assert.match(String(inspection), /[A-Z][a-z]{2}-\d{2}/, 'keyboard inspection shows the selected period')
  assert.ok(String(inspection).includes(rowFocus.period), `Enter on the focused row inspects ITS period (${rowFocus.period})`)
  const selectedPeriod = await evalProbe(run, `(() => { const row = document.querySelector('[data-testid="nav-echarts-pilot"] tbody tr[aria-selected="true"]'); return row ? (row.querySelector('.chart-table__period')?.childNodes[0]?.textContent ?? '').trim() : null })()`)
  assert.equal(selectedPeriod, rowFocus.period, 'the Enter-inspected row is the aria-selected row')

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

  // COMPATIBLE refresh: one re-issued query answered with the same document
  // identity; BOTH zoom bounds retained.
  const compatibleBefore = navRequestCount(fixtureServer)
  await run(['eval', `(() => {
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

  // INCOMPATIBLE refresh: every period key differs, so BOTH bounds must reset
  // to the new document's full range — never leak.
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
  fixtureServer.charts.scenario = 'v2'

  // Parked response: the previous chart stays visibly loading, never looking
  // current with new labels.
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

  await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
  await run(['wait', '150'])
  await shoot('d8-nav-modern.png')

  // --- allocation states on the default-on build ----------------------------
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
  await shoot('d8-allocation-ineligible.png')

  chartsC4.breakdownScenario = 'malformed'
  const malformedBefore = breakdownRequestCount(fixtureServer)
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="allocation-assetType-error"]') !== null`)
  await run(['wait', '700'])
  assert.equal(breakdownRequestCount(fixtureServer) - malformedBefore, 1, 'malformed v2: exactly one request, no retry loop')

  chartsC4.breakdownScenario = 'legacy'
  await run(['reload'])
  await run(['wait', '2000'])
  await waitFor(run, `document.querySelector('[data-testid="allocation-capability-notice"]') !== null && [...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3`)
  const legacyNotice = await evalProbe(run, `document.querySelector('[data-testid="allocation-capability-notice"]')?.innerText ?? ''`)
  assert.match(String(legacyNotice), /legacy response/, 'legacy-only shows the honest capability notice')
  chartsC4.breakdownScenario = 'v2'
  await run(['reload'])
  await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3`)
  await run(['wait', '600'])

  // --- security histories on the default-on build ---------------------------
  await run(['open', `${appOrigin}/database/securities/1`])
  await run(['wait', '400'])
  const stockState = await evalProbe(run, `(() => {
    const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]
    return { tables: tables.length, texts: tables.map((t) => t.innerText) }
  })()`)
  assert.equal(stockState.tables, 2, 'stock: both modern histories render with exact tables')
  assert.match(String(stockState.texts[0]), /\$102\.25/, 'price table keeps exact dollar displays')
  assert.match(String(stockState.texts[0]), /carried forward|Aug 20, 2026/, 'price table lists the annotated carry-forward observation')
  assert.match(String(stockState.texts[1]), /8\.000000000/, 'position table keeps exact quantities')
  await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
  await run(['wait', '150'])
  await shoot('d8-security-stock.png')

  // Renderer failure with explicit recovery: retry first (fails again), then
  // the user-chosen fallback.
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

  // Zoom, then switch context: the view-only zoom resets with the new
  // security and no stock point leaks into the bond tooltip.
  await run(['open', `${appOrigin}/database/securities/1`])
  await waitFor(run, `document.querySelectorAll('.echarts-security canvas').length >= 1`)
  await run(['wait', '400'])
  await run(['eval', `(() => {
    const host = document.querySelector('.echarts-security')
    host.__c4DispatchAction({ type: 'dataZoom', start: 40, end: 70 })
    return true
  })()`])
  await run(['wait', '300'])
  await run(['open', `${appOrigin}/database/securities/2`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
  await run(['wait', '300'])
  const bondState = await evalProbe(run, `(() => {
    const tables = [...document.querySelectorAll('[data-testid="security-data-table"]')]
    return { tables: tables.length, text: tables[0]?.innerText ?? '' }
  })()`)
  assert.match(String(bondState.text), /99\.875% of nominal/, 'bond price table keeps percent-of-nominal displays')
  assert.equal(bondState.tables, 2, 'bond: both histories render')
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
  const bondErrors = await runAgentBrowser({ args: ['errors'], context: 'd8 bond errors', initScript, log, session })
  assert.deepEqual(bondErrors.errors, [], 'switching securities after zoom leaves no page errors')
  await run(['eval', `(() => { document.querySelector('#security-price-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
  await run(['wait', '150'])
  await shoot('d8-security-bond.png')

  await run(['open', `${appOrigin}/database/securities/3`])
  await waitFor(run, `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
  const cryptoState = await evalProbe(run, `[...document.querySelectorAll('[data-testid="security-data-table"]')].map((t) => t.innerText).join('\\n')`)
  assert.match(String(cryptoState), /0\.000216590/, 'crypto position table keeps exact quantity precision')
  await run(['eval', `(() => { document.querySelector('#security-position-history').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
  await run(['wait', '150'])
  await shoot('d8-security-crypto.png')

  // --- mobile containment + real pointer tooltip -----------------------------
  await run(['open', `${appOrigin}/dashboard`])
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '600'])
  const headerBottom = await evalProbe(run, `document.querySelector('.v-app-bar')?.getBoundingClientRect().bottom ?? 0`)
  const mobileHit = await evalProbe(run, `(() => {
    const headerBottom = ${JSON.stringify(headerBottom)}
    const targets = [
      ...document.querySelectorAll('[data-series-id]'),
      ...document.querySelectorAll('[data-testid="allocation-legend"] button'),
      ...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] .v-tab'),
      ...document.querySelectorAll('.chart-inspection select, .chart-inspection__reset'),
    ]
    return targets.map((element) => {
      element.scrollIntoView({ block: 'center' })
      window.scrollBy(0, element.getBoundingClientRect().top - headerBottom - 8)
      const rect = element.getBoundingClientRect()
      const hitElement = document.elementFromPoint(
        Math.min(Math.max(rect.left + rect.width / 2, 4), window.innerWidth - 4),
        Math.max(rect.top + rect.height / 2, headerBottom + 8),
      )
      return { hittable: hitElement === element || element.contains(hitElement) }
    })
  })()`)
  assert.ok(mobileHit.length >= 8, 'mobile: combined-page controls present')
  for (const entry of mobileHit) {
    assert.equal(entry.hittable, true, 'mobile: control actually hittable and clear of the fixed header')
  }

  // NAV mobile tooltip via the C3 capture tooling: a real two-step pointer
  // sweep over CDP with full-visibility verification (synthetic mousemove
  // events do not reliably drive ECharts' canvas hit-test).
  await run(['eval', `(() => { window.__c3CaptureTab = true; return true })()`])
  const mobileCapture = await new Promise((resolveSpawn) => {
    const child = spawn(process.execPath, [resolve(frontendRoot, 'scripts/qa-tooltip-capture.mjs'), String(cdpUrl), appOrigin, resolve(D8_ASSETS(frontendRoot), 'd8-nav-mobile-tooltip.png'), '0.5'], { stdio: 'pipe' })
    let out = ''
    child.stdout.on('data', (chunk) => { out += chunk })
    child.stderr.on('data', (chunk) => { out += chunk })
    child.on('error', (error) => resolveSpawn({ code: -1, out: String(error) }))
    child.on('close', (code) => resolveSpawn({ code, out }))
  })
  assert.equal(mobileCapture.code, 0, `mobile tooltip must be captured fully visible (${mobileCapture.out.slice(-600)})`)
  captures.push('d8-nav-mobile-tooltip.png')
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '500'])

  // --- native 200% zoom (real DPR change, then reset) ------------------------
  await run(['eval', `(() => { window.__c3CaptureTab = true; return true })()`])
  await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
  await run(['wait', '150'])
  const zoomScript = await new Promise((resolveSpawn, rejectSpawn) => {
    const child = spawn(process.execPath, [resolve(frontendRoot, 'scripts/qa-native-zoom.mjs'), String(cdpUrl), appOrigin, '200'], { stdio: 'pipe' })
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
  assert.equal(zoomedProbe.dpr, 2, 'native zoom really changed the DPR to 2')
  assert.equal(zoomedProbe.pilot, true, 'native 200%: NAV pilot still renders')
  assert.equal(zoomedProbe.legends, 3, 'native 200%: allocation legends still render')
  // Containment + fixed-header clearance at native zoom: the primary controls
  // sit inside the viewport and clear the (taller at 200%) app bar.
  const zoomHit = await evalProbe(run, `(() => {
    const bar = document.querySelector('.v-app-bar')
    const barBottom = bar ? bar.getBoundingClientRect().bottom : 0
    const targets = [
      ...document.querySelectorAll('[data-series-id]'),
      ...document.querySelectorAll('[data-testid="allocation-legend"] button'),
    ]
    return targets.map((element) => {
      element.scrollIntoView({ block: 'center' })
      window.scrollBy(0, element.getBoundingClientRect().top - barBottom - 8)
      const rect = element.getBoundingClientRect()
      const hitElement = document.elementFromPoint(
        Math.min(Math.max(rect.left + rect.width / 2, 4), window.innerWidth - 4),
        Math.max(rect.top + rect.height / 2, barBottom + 8),
      )
      return {
        hittable: hitElement === element || element.contains(hitElement),
        inside: rect.left >= -1 && rect.right <= window.innerWidth + 1,
      }
    })
  })()`)
  for (const entry of zoomHit) {
    assert.equal(entry.hittable, true, 'native 200%: control hittable and clear of the taller app bar')
    assert.equal(entry.inside, true, 'native 200%: control inside the viewport')
  }
  await shoot('d8-native-zoom.png')
  await new Promise((resolveSpawn) => {
    const child = spawn(process.execPath, [resolve(frontendRoot, 'scripts/qa-native-zoom.mjs'), String(cdpUrl), appOrigin, '100'], { stdio: 'ignore' })
    child.on('error', () => {})
    child.on('close', () => resolveSpawn())
  })
  const dprReset = await evalProbe(run, `window.devicePixelRatio`)
  assert.equal(dprReset, 1, 'native zoom reset restores DPR 1')
}

// ---------------------------------------------------------------------------
// Phase D: default-on rendered states (subset with own captures; the FULL
// rendered-state matrix remains the d5 case on the rollback artifact).
// ---------------------------------------------------------------------------
async function assertD8RenderedStates({ appOrigin, fixtureServer, frontendRoot, run, captures }) {
  const shoot = async (name, expectedPath) => {
    // A capture named for a route must be taken on that route: assert the
    // current path first (two captures were previously taken after the flow
    // had already navigated to FX).
    if (expectedPath) {
      const current = await evalProbe(run, 'location.pathname')
      assert.equal(current, expectedPath, `capture ${name} must be shot on ${expectedPath} (found ${current})`)
    }
    await run(['screenshot', resolve(D8_ASSETS(frontendRoot), name)])
    captures.push(name)
  }
  const open = async (route, ready) => {
    await run(['open', `${appOrigin}${route}`])
    await waitFor(run, `document.querySelector('[data-testid="route-content"]') !== null`)
    await run(['wait', '500'])
    if (ready) await waitFor(run, ready, 8000).catch(() => {})
  }
  const textOf = (sel) => evalProbe(run, `document.querySelector('${sel}')?.textContent ?? document.body.innerText`)
  const searchNoMatch = async (route) => {
    await open(route, `document.querySelector('.workspace-table-toolbar input') !== null`)
    await run(['eval', `(() => { const input = document.querySelector('.workspace-table-toolbar input'); input.value = 'zzz-no-match'; input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
    await run(['wait', '900'])
    const probe = await textOf('.v-data-table')
    assert.ok(probe.toLowerCase().includes('no data available'), `filtered-empty: ${route} renders a server-owned no-match response`)
  }

  // --- EMPTY state (every family the d5 machine covers) ---------------------
  fixtureServer.setD5State('empty')
  await open('/summary')
  let probe = await textOf('main')
  assert.ok(probe.includes('No account performance data'), 'summary empty performance state')
  assert.ok(probe.includes('No breakdown data'), 'summary empty breakdown state')
  probe = await evalProbe(run, `(() => { const sel = document.querySelector('[data-testid="performance-view-select"]'); return sel ? sel.classList.contains('v-input--disabled') || !!sel.querySelector('input[disabled]') : null })()`)
  assert.equal(probe, true, 'summary period controls disabled for empty data')
  await shoot('d8-summary-empty.png', '/summary')

  for (const [route, marker] of [
    ['/database/brokers', 'Add Broker'],
    ['/database/accounts', 'Add Account'],
    ['/database/securities', 'Record Merger'],
  ]) {
    await open(route, `document.querySelectorAll('.v-data-table tbody tr').length >= 0 && document.querySelector('.v-data-table') !== null`)
    probe = await textOf('.v-data-table')
    assert.ok(probe.toLowerCase().includes('no data available'), `empty: ${route} renders the no-data state`)
    probe = await textOf('main')
    assert.ok(probe.includes(marker), `empty: ${route} keeps its primary actions (${marker})`)
    if (route === '/database/securities') await shoot('d8-securities-empty.png', route)
  }

  await open('/database/prices', `document.querySelector('.v-data-table') !== null`)
  probe = await textOf('.v-data-table')
  assert.ok(probe.includes('Apply Filters'), 'prices empty state keeps its guided Apply Filters text')
  await open('/database/fx', `document.querySelector('.v-data-table') !== null`)
  probe = await evalProbe(run, `(() => ({ headers: [...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim()), addAction: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Add FX Rate') }))()`)
  assert.deepEqual(probe.headers, ['Date'], 'fx empty pivot renders the Date column only')
  assert.equal(probe.addAction, true, 'fx keeps Add FX Rate in the empty state')
  await shoot('d8-fx-empty.png', '/database/fx')

  // --- ERROR state (every family with a retry surface + settings) -----------
  // Readability regression for the alert Retry actions: the elevated default
  // rendered white text on its own white background (computed contrast 1.0).
  const assertRetryReadable = async (testId) => {
    const style = await evalProbe(run, `(() => {
      const btn = document.querySelector('[data-testid="${testId}"]')
      if (!btn) return { missing: true }
      const lum = (rgbStr) => {
        const parts = rgbStr.match(/\\d+(\\.\\d+)?/g).map(Number)
        const ch = [parts[0], parts[1], parts[2]].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) })
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
      }
      const contrast = (a, b) => { const l1 = lum(a); const l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05) }
      const cs = getComputedStyle(btn)
      const alert = btn.closest('.v-alert')
      const alertBg = alert ? getComputedStyle(alert).backgroundColor : 'rgb(255, 255, 255)'
      return {
        variantText: btn.className.includes('v-btn--variant-text'),
        label: (btn.querySelector('.v-btn__content') ?? btn).textContent.trim(),
        contrastVsOwnBg: Number(contrast(cs.color, cs.backgroundColor).toFixed(2)),
        contrastVsAlertBg: Number(contrast(cs.color, alertBg).toFixed(2)),
      }
    })()`)
    assert.equal(style.missing, undefined, `rendered readability: ${testId} rendered`)
    assert.equal(style.label, 'Retry', `rendered readability: ${testId} label intact`)
    assert.equal(style.variantText, true, `rendered readability: ${testId} uses the text variant`)
    assert.ok(style.contrastVsOwnBg >= 4.5, `rendered readability: ${testId} label readable against its own background (contrast ${style.contrastVsOwnBg})`)
    assert.ok(style.contrastVsAlertBg >= 4.5, `rendered readability: ${testId} label readable against the alert background (contrast ${style.contrastVsAlertBg})`)
  }
  fixtureServer.setD5State('error')
  await open('/summary')
  await waitFor(run, `document.body.innerText.includes('Unable to load part of the summary')`, 8000).catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load part of the summary'), 'summary error state')
  for (const route of ['/database/brokers', '/database/accounts', '/database/securities']) {
    await open(route)
    await waitFor(run, `document.body.innerText.includes('Unable to load this table')`, 8000).catch(() => {})
    probe = await textOf('main')
    assert.ok(probe.includes('Unable to load this table'), `error: ${route} renders the retry state`)
    if (route === '/database/brokers') await shoot('d8-brokers-error.png', route)
    await assertRetryReadable('table-retry')
  }
  await open('/database/prices')
  await waitFor(run, `document.body.innerText.includes('Unable to load prices or filters')`, 8000).catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load prices or filters'), 'prices error state')
  await assertRetryReadable('prices-retry')
  await open('/database/fx')
  await waitFor(run, `document.body.innerText.includes('Unable to load exchange rates')`, 8000).catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load exchange rates'), 'fx error state')
  await open('/profile/settings')
  await waitFor(run, `document.body.innerText.includes('Failed to load settings')`, 8000).catch(() => {})
  probe = await textOf('body')
  assert.ok(probe.includes('Failed to load settings'), 'settings error state surfaces the page-owned failure')
  await shoot('d8-settings-error.png', '/profile/settings')

  // --- FILTERED-EMPTY (genuine server-side filtering on a no-match search) --
  fixtureServer.setD5State('populated')
  await searchNoMatch('/database/brokers')
  await shoot('d8-brokers-filtered-empty.png', '/database/brokers')
  await searchNoMatch('/database/accounts')
  await searchNoMatch('/database/securities')
  await open('/database/fx', `document.querySelector('.workspace-table-toolbar input') !== null`)
  await run(['eval', `(() => { const input = document.querySelector('.workspace-table-toolbar input'); input.value = 'zzz-no-match'; input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
  await run(['wait', '900'])
  probe = await evalProbe(run, `[...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim())`)
  assert.deepEqual(probe, ['Date'], 'fx filtered-empty drops every pair column')
  await shoot('d8-fx-filtered-empty.png', '/database/fx')

  // --- LOGIN error (public session; 401 renders a readable on-page error) ---
  fixtureServer.setD5State('error')
  const loginSession = `d8-states-login-${process.pid}`
  const loginRun = (args) => runAgentBrowser({ args, context: 'd8 states login', initScript: undefined, log: async () => {}, session: loginSession })
  await loginRun(['open', `${appOrigin}/login`])
  await loginRun(['wait', '400'])
  await loginRun(['eval', `(() => { const user = document.querySelector('input[autocomplete="username"]'); const pass = document.querySelector('input[autocomplete="current-password"]'); if (!user || !pass) throw new Error('login fields missing'); user.value = 'fixture-user'; user.dispatchEvent(new Event('input', { bubbles: true })); pass.value = 'wrong-password'; pass.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
  await loginRun(['eval', `(() => { document.querySelector('button[type="submit"]')?.click(); return true })()`])
  await loginRun(['wait', '--fn', `!!document.querySelector('[role="alert"], .v-alert') || document.body.innerText.toLowerCase().includes('invalid') || document.body.innerText.toLowerCase().includes('credential')`, '--timeout', '8000']).catch(() => {})
  const loginText = (await loginRun(['eval', 'document.body.innerText'])).result
  assert.match(String(loginText), /invalid|credential|error|denied|failed/i, 'login error state surfaces a readable error summary')
  assert.equal((await loginRun(['eval', 'location.pathname'])).result, '/login', 'failed login stays on the login page')
  await loginRun(['close'])

  fixtureServer.setD5State('populated')
}

export async function runFinalQaD8Flow({ frontendRoot, browserDir, artifactsDir, screenshotsDir, browserLog }) {
  const log = async (entry) => {
    lastActivity = Date.now()
    await appendFile(browserLog, `${JSON.stringify(entry)}\n`, 'utf8')
  }
  await writeFile(browserLog, '', 'utf8')
  const authInit = resolve(browserDir, 'auth-init.js')
  await mkdir(artifactsDir, { recursive: true })
  await mkdir(screenshotsDir, { recursive: true })
  const assetsDir = D8_ASSETS(frontendRoot)
  await mkdir(assetsDir, { recursive: true })

  // Keep the event loop alive and force an attributable exit if the
  // post-phase teardown ever stalls (a silently unsettled top-level await
  // would otherwise exit 13 with no diagnostic).
  let lastActivity = Date.now()
  const settleWatchdog = setInterval(() => {
    if (Date.now() - lastActivity > 180_000) {
      console.error(`D8 ERROR: no harness activity for 180s (last ${new Date(lastActivity).toISOString()}); forcing exit 1`)
      process.exit(1)
    }
  }, 30_000)
  const sessions = new Map()
  const routeFailures = []
  const matrixRows = []
  const workflowResults = []
  // Every fixture server's unmatched requests are aggregated here (the base
  // smoke runner fails its run on them; a family swap must not discard them).
  const fixtureMismatches = []
  const harvestUnmatched = (server) => {
    fixtureMismatches.push(...collectFixtureMismatches(server))
  }
  const captures = []
  let delivery = null
  // Shared across phases; closed via the harness cleanup on any exit path.
  let fixtureServer = null
  let defaultOnApp = null
  let rollbackApp = null
  let artifactRecordsRef = null

  const closeSession = (session, initScript) =>
    runAgentBrowser({ args: ['close'], context: `${session} close`, initScript, log, session })

  const launchSession = async (name, { origin, authenticated, viewport, initScript }) => {
    const session = `${name}-${process.pid}`
    sessions.set(session, initScript)
    await runAgentBrowser({
      args: ['open', `${origin}${routes.find((route) => route.authenticated === authenticated).path}`],
      context: `${name} launch ${authenticated ? 'authenticated' : 'public'} session`,
      initScript,
      log,
      session,
    })
    await runAgentBrowser({
      args: ['set', 'viewport', String(viewport.width), String(viewport.height)],
      context: `${name} set viewport`,
      initScript,
      log,
      session,
    })
    return session
  }

  try {
    await runBrowserHarnessLifecycle({
    run: async () => {
      // ONE fixture server for every phase. The artifact builds MUST happen
      // with its origin baked in as VITE_API_URL (the app's axios baseURL —
      // without it every API request hits the static app server, whose SPA
      // fallback answers API paths with index.html). Phase-local scenario
      // machines (charts, chartsC4, d5 states) are restored before the next
      // phase uses them.
      fixtureServer = await startFixtureServer({
        d4Flow: true,
        chartsC2Flow: true,
        chartsC3Flow: true,
        chartsC4Flow: true,
        settingsAccountFlow: true,
        importsD6Flow: true,
        brokersSecurityD7Flow: true,
        d5States: true,
      })
      try {
        // --- Phase A: artifact establishment ------------------------------------
        const envScan = await scanFlagEnvFiles(frontendRoot)
        assert.deepEqual(
          envScan.flagKeysFound,
          [],
          `the default-on candidate must be genuinely unflagged — release flags found in env files: ${JSON.stringify(envScan.flagKeysFound)}`,
        )
        const defaultOnDir = resolve(artifactsDir, 'app-d8-default-on')
        const rollbackDir = resolve(artifactsDir, 'app-d8-rollback')
        console.log('D8 building app-d8-default-on (all three VITE_*_ECHARTS_ENABLED keys genuinely absent)...')
        await withFlagEnvironment(
          {
            VITE_NAV_ECHARTS_ENABLED: null,
            VITE_ALLOCATION_ECHARTS_ENABLED: null,
            VITE_SECURITY_ECHARTS_ENABLED: null,
            VITE_API_URL: fixtureServer.origin,
          },
          () => buildFlagArtifact(frontendRoot, defaultOnDir, {}),
        )
        console.log('D8 building app-d8-rollback (all three keys explicitly false)...')
        await withFlagEnvironment(
          {
            VITE_NAV_ECHARTS_ENABLED: 'false',
            VITE_ALLOCATION_ECHARTS_ENABLED: 'false',
            VITE_SECURITY_ECHARTS_ENABLED: 'false',
            VITE_API_URL: fixtureServer.origin,
          },
          () => buildFlagArtifact(frontendRoot, rollbackDir, {}),
        )
        artifactRecordsRef = {
          defaultOn: { dir: 'tests/browser/artifacts/app-d8-default-on', flags: 'absent (default-on policy)', hash: await hashArtifact(defaultOnDir) },
          rollback: { dir: 'tests/browser/artifacts/app-d8-rollback', flags: "VITE_NAV_ECHARTS_ENABLED=false, VITE_ALLOCATION_ECHARTS_ENABLED=false, VITE_SECURITY_ECHARTS_ENABLED=false", hash: await hashArtifact(rollbackDir) },
          envScan,
        }
        await writeFile(resolve(artifactsDir, 'final-qa-d8-artifacts.json'), `${JSON.stringify(artifactRecordsRef, null, 2)}\n`)

        defaultOnApp = await startBuiltAppServer(defaultOnDir)
        rollbackApp = await startBuiltAppServer(rollbackDir)
        {
          // --- Phase B: default-on full route matrix (18 routes x 5 viewports) --
          // Chart flows on: the base fixtures' all-selection context matches
          // the C2/C4 chart envelopes, so chartful routes render the modern
          // default-on charts the captures document. Every other special
          // flow stays off (they own endpoints the matrix probes plain).
          fixtureServer.setFixtureModes({
            d4Flow: false,
            settingsAccountFlow: false,
            importsD6Flow: false,
            brokersSecurityD7Flow: false,
          })
          const matrixApp = defaultOnApp
          for (const viewport of D8_VIEWPORTS) {
          for (const authenticated of [false, true]) {
            const selectedRoutes = routes.filter((route) => route.authenticated === authenticated)
            const session = await launchSession(`d8-matrix-${authenticated ? 'auth' : 'public'}-${viewport.name}`, { origin: matrixApp.origin, authenticated, viewport, initScript: authenticated ? authInit : undefined })
            for (const route of selectedRoutes) {
              const row = { matrix: 'default-on', route: route.path, viewport: viewport.name }
              try {
                await runRoute({ appOrigin: matrixApp.origin, authenticated, route, session, viewport, log })
                const captureName = MATRIX_CAPTURES[`${viewport.name} ${route.path}`]
                if (captureName) {
                  await runAgentBrowser({ args: ['screenshot', resolve(assetsDir, captureName)], context: `${viewport.name} ${route.path} capture`, initScript: authenticated ? authInit : undefined, log, session })
                  captures.push(captureName)
                }
                row.result = 'pass'
                console.log(`D8-DEFAULT-ON PASS ${viewport.name} ${route.path}`)
              } catch (error) {
                row.result = 'fail'
                row.error = error.message
                routeFailures.push(row)
                console.error(`D8-DEFAULT-ON FAIL ${viewport.name} ${route.path}: ${error.message}`)
                try {
                  await runAgentBrowser({ args: ['screenshot', resolve(screenshotsDir, `d8-fail-${viewport.name}-${route.path.replaceAll('/', '-')}.png`)], context: `${viewport.name} ${route.path} failure capture`, initScript: authenticated ? authInit : undefined, log, session })
                } catch (screenshotError) {
                  await log({ context: `${viewport.name} ${route.path}`, screenshotError: screenshotError.message })
                }
              }
              matrixRows.push(row)
            }
            await closeSession(session, authenticated ? authInit : undefined)
            sessions.delete(session)
          }
        }

        // --- Delivery remeasure on the default-on artifact (cold graphs) ------
        // /login is measured on a public session; authenticated routes on a
        // separate auth session, matching the rollback delivery case.
        const measure = async (sessionName, initScript, path, canvasWait) => {
          const session = `d8-delivery-${sessionName}-${process.pid}`
          const run = (args) => runAgentBrowser({ args, context: `delivery ${path}`, initScript, log, session })
          if (!sessions.has(session)) {
            sessions.set(session, initScript)
            await run(['open', `${matrixApp.origin}${path}`])
            await run(['set', 'viewport', '1440', '1000'])
          } else {
            await run(['open', `${matrixApp.origin}${path}`])
          }
          if (canvasWait) await waitFor(run, canvasWait, 20000)
          await run(['wait', '--load', 'networkidle'])
          const observed = await run(['eval', `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`])
          return measureRouteBundles({ root: defaultOnDir, resources: observed.result })
        }
        const publicDelivery = 'public'
        const authDelivery = 'auth'
        const loginGraph = await measure(publicDelivery, undefined, '/login', null)
        const profileGraph = await measure(authDelivery, authInit, '/profile', `document.body.innerText.length > 100`)
        const transactionsGraph = await measure(authDelivery, authInit, '/transactions', `document.body.innerText.length > 100`)
        const securityGraph = await measure(authDelivery, authInit, '/database/securities/1', `document.querySelectorAll('[data-testid="security-data-table"]').length === 2`)
        const dashboardGraph = await measure(authDelivery, authInit, '/dashboard', `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3 && !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas')`)
        // login/profile/transactions must stay chart-runtime free on the
        // default-on build (the modern dashboard/security routes carry it).
        for (const [name, graph] of [['login', loginGraph], ['profile', profileGraph], ['transactions', transactionsGraph]]) {
          assert.equal(CHARTJS_RUNTIME.test(graph.modules.join('\n')), false, `${name}: no Chart.js runtime module on the cold default-on route`)
          assert.equal(ECHARTS_RUNTIME.test(graph.modules.join('\n')), false, `${name}: no ECharts runtime module on the cold default-on route`)
        }
        for (const [name, graph] of [['login', loginGraph], ['profile', profileGraph], ['transactions', transactionsGraph], ['securityDetail', securityGraph]]) {
          assert.ok(graph.gzipJsCss > 0, `${name}: complete graph measured`)
          assert.equal(graph.modules.some((path) => /\/components\/dialogs\//.test(path)), false, `${name}: unopened dialog modules downloaded`)
        }
        const D8_DASHBOARD_BUDGET = 535_000
        delivery = {
          note: 'gzip+raw JS/CSS over the observed per-route cold resource graph on the app-d8-default-on artifact. Loopback timings are not production latency evidence. The dashboard target is the saved C5a cutover target (~535 kB gzip); the 401 kB legacy budget is asserted by the rollback delivery case.',
          dashboard: { gzip: dashboardGraph.gzipJsCss, raw: dashboardGraph.files.reduce((t, f) => t + f.bytes, 0), targetGzip: D8_DASHBOARD_BUDGET, withinTarget: dashboardGraph.gzipJsCss <= D8_DASHBOARD_BUDGET },
          login: { gzip: loginGraph.gzipJsCss, raw: loginGraph.files.reduce((t, f) => t + f.bytes, 0) },
          profile: { gzip: profileGraph.gzipJsCss, raw: profileGraph.files.reduce((t, f) => t + f.bytes, 0) },
          transactions: { gzip: transactionsGraph.gzipJsCss, raw: transactionsGraph.files.reduce((t, f) => t + f.bytes, 0) },
          securityDetail: { gzip: securityGraph.gzipJsCss, raw: securityGraph.files.reduce((t, f) => t + f.bytes, 0) },
        }
        assert.equal(delivery.dashboard.withinTarget, true, `all-modern dashboard ${delivery.dashboard.gzip} gzip bytes exceeds the saved ~535 kB cutover target`)
        console.log(`D8-DEFAULT-ON MEASURE delivery: dashboard ${delivery.dashboard.gzip}, login ${delivery.login.gzip}, profile ${delivery.profile.gzip}, transactions ${delivery.transactions.gzip}, security ${delivery.securityDetail.gzip} gzip bytes`)
        for (const [sessionName, initScript] of [[publicDelivery, undefined], [authDelivery, authInit]]) {
          const session = `d8-delivery-${sessionName}-${process.pid}`
          await closeSession(session, initScript)
          sessions.delete(session)
        }

        // --- Phase B2: long-name pass (representative dense routes) -----------
        // longAccount changes the committed account selection, which no longer
        // matches the C2/C4 chart envelopes' all-selection context — chartful
        // routes would legacy-fallback for fixture reasons, so this pass
        // captures non-chart routes only and skips chart assertions.
        fixtureServer.setFixtureModes({ chartsC2Flow: false, chartsC3Flow: false, chartsC4Flow: false, longAccount: true })
        const longNameRoutes = ['/open-positions', '/closed-positions', '/transactions', '/summary', '/database/accounts', '/profile/settings']
        const longNameViewports = [D8_VIEWPORTS[0], D8_VIEWPORTS[2]]
        for (const viewport of longNameViewports) {
          const session = await launchSession(`d8-longnames-${viewport.name}`, { origin: matrixApp.origin, authenticated: true, viewport, initScript: authInit })
          for (const routePath of longNameRoutes) {
            const route = routes.find((entry) => entry.path === routePath)
            const row = { matrix: 'default-on-longnames', route: route.path, viewport: viewport.name }
            try {
              await runRoute({ appOrigin: matrixApp.origin, authenticated: true, route, session, viewport, log })
              const captureName = LONGNAME_CAPTURES[`${viewport.name} ${route.path}`]
              if (captureName) {
                await runAgentBrowser({ args: ['screenshot', resolve(assetsDir, captureName)], context: `${viewport.name} ${route.path} long-name capture`, initScript: authInit, log, session })
                captures.push(captureName)
              }
              row.result = 'pass'
              console.log(`D8-DEFAULT-ON-LONGNAMES PASS ${viewport.name} ${route.path}`)
            } catch (error) {
              row.result = 'fail'
              row.error = error.message
              routeFailures.push(row)
              console.error(`D8-DEFAULT-ON-LONGNAMES FAIL ${viewport.name} ${route.path}: ${error.message}`)
            }
            matrixRows.push(row)
          }
          await closeSession(session, authInit)
          sessions.delete(session)
        }
        fixtureServer.setFixtureModes({ longAccount: false })
      }

      // --- Phase C: integrated workflows + charts on the default-on artifact --
      // Each workflow family runs against a PRISTINE fixture server on the
      // SAME fixed port (the app under test bakes one fixture origin at build
      // time, so the port must survive the swap), with only that family's mode
      // enabled — reproducing exactly the conditions each focused case was
      // proven under. Cross-family fixture state (d4's reporting-currency
      // mutation, the import flow's appended brokers, the settings selection
      // machine) therefore cannot leak between families.
      const fixturePort = Number(new URL(fixtureServer.origin).port)
      const swapFixtureServer = async (modes) => {
        harvestUnmatched(fixtureServer)
        await fixtureServer.close().catch(() => undefined)
        fixtureServer = await startFixtureServer({ ...modes, port: fixturePort })
      }
      const TRANSIENT_ERROR = /unknown JSON envelope|No connection could be made|actively refused|appChildren: 0|Daemon version mismatch/
      let workflowSessionRef = null
      const runWorkflow = async (name, fn) => {
        try {
          try {
            await fn()
            workflowResults.push({ workflow: name, result: 'pass' })
            console.log(`D8-DEFAULT-ON PASS workflow ${name}`)
            return
          } catch (firstError) {
            if (!TRANSIENT_ERROR.test(firstError.message)) throw firstError
            console.warn(`D8-DEFAULT-ON RETRY workflow ${name} after transient error: ${firstError.message}`)
            await new Promise((resolve) => setTimeout(resolve, 5000))
          }
          await fn()
          workflowResults.push({ workflow: name, result: 'pass', retriedAfter: 'transient daemon/connection error' })
          console.log(`D8-DEFAULT-ON PASS workflow ${name} (after transparent transient retry)`)
        } catch (error) {
          workflowResults.push({ workflow: name, result: 'fail', error: error.message })
          routeFailures.push({ matrix: 'default-on', workflow: name, error: error.message })
          console.error(`D8-DEFAULT-ON FAIL workflow ${name}: ${error.message}`)
          try {
            const failureState = await runAgentBrowser({ args: ['eval', `(() => ({
              path: location.pathname,
              dpr: window.devicePixelRatio,
              accountSelection: localStorage.getItem('accountSelection'),
              bodyHead: document.body.innerText.slice(0, 300).split(String.fromCharCode(10)).join(' | '),
            }))()`], context: `workflow failure state ${name}`, initScript: authInit, log, session: workflowSessionRef })
            const settingsState = fixtureServer.settingsAccount ? {
              profileWrites: fixtureServer.settingsAccount.profileWrites && fixtureServer.settingsAccount.profileWrites.length,
              accountWrites: fixtureServer.settingsAccount.accountWrites && fixtureServer.settingsAccount.accountWrites.length,
              dashboardWrites: fixtureServer.settingsAccount.dashboardWrites && fixtureServer.settingsAccount.dashboardWrites.length,
              selection: fixtureServer.settingsAccount.selection,
            } : null
            console.error(`D8 WORKFLOW FAILURE STATE ${name}: session=${JSON.stringify(failureState.result).slice(0, 500)} fixture=${JSON.stringify(settingsState)}`)
            await runAgentBrowser({ args: ['screenshot', resolve(screenshotsDir, `d8-workflow-fail-${name.replaceAll(/[^a-z0-9]+/gi, '-')}.png`)], context: `workflow failure capture ${name}`, initScript: authInit, log, session: workflowSessionRef })
          } catch (diagnosticError) {
            await log({ workflow: name, diagnosticError: diagnosticError.message })
          }
        }
      }
      {
        // d4 family: dense tables and transactions.
        await swapFixtureServer({ d4Flow: true })
        const desktop = await launchSession('d8-flows-desktop', { origin: defaultOnApp.origin, authenticated: true, viewport: { width: 1440, height: 1000 }, initScript: authInit })
        workflowSessionRef = desktop

        await runWorkflow('d4-tables-desktop', () => assertD4TablesFlow({ appOrigin: defaultOnApp.origin, context: 'd8 d4 tables', initScript: authInit, log, session: desktop, fixtureServer }))
        await runWorkflow('d4-transactions-desktop', () => assertD4TransactionsFlow({ appOrigin: defaultOnApp.origin, context: 'd8 d4 transactions', initScript: authInit, log, session: desktop, fixtureServer }))
        for (const route of ['/open-positions', '/closed-positions', '/transactions']) {
          await runWorkflow(`d4-viewport-desktop ${route}`, () => assertD4ViewportChecks({ appOrigin: defaultOnApp.origin, context: `d8 d4 viewport desktop ${route}`, initScript: authInit, log, session: desktop, viewport: { name: 'desktop', width: 1440, height: 1000 }, route }))
        }
        const mobile = await launchSession('d8-flows-mobile', { origin: defaultOnApp.origin, authenticated: true, viewport: { width: 390, height: 844 }, initScript: authInit })
        for (const route of ['/open-positions', '/closed-positions', '/transactions']) {
          await runWorkflow(`d4-viewport-mobile ${route}`, () => assertD4ViewportChecks({ appOrigin: defaultOnApp.origin, context: `d8 d4 viewport mobile ${route}`, initScript: authInit, log, session: mobile, viewport: { name: 'mobile', width: 390, height: 844 }, route }))
        }

        // d7 family: broker/security extraction flows, one session per
        // viewport (the flow switches viewports internally).
        await swapFixtureServer({ brokersSecurityD7Flow: true })
        await runWorkflow('brokers-security-d7-desktop', () => assertBrokersSecurityD7Flow({ appOrigin: defaultOnApp.origin, context: 'd8 brokers d7 desktop', initScript: authInit, log, session: desktop, fixtureServer, viewport: { name: 'desktop', width: 1440, height: 1000 } }))
        await runWorkflow('brokers-security-d7-mobile', async () => {
          const d7Mobile = await launchSession('d8-d7-mobile', { origin: defaultOnApp.origin, authenticated: true, viewport: { width: 390, height: 844 }, initScript: authInit })
          workflowSessionRef = d7Mobile
          try {
            await assertBrokersSecurityD7Flow({ appOrigin: defaultOnApp.origin, context: 'd8 brokers d7 mobile', initScript: authInit, log, session: d7Mobile, fixtureServer, viewport: { name: 'mobile', width: 390, height: 844 } })
          } finally {
            await closeSession(d7Mobile, authInit)
            sessions.delete(d7Mobile)
          }
          workflowSessionRef = desktop
        })

        // Import family: loopback WebSocket flows.
        await swapFixtureServer({ importsD6Flow: true })
        await runWorkflow('imports-d6-desktop', () => assertImportsD6Flow({ appOrigin: defaultOnApp.origin, context: 'd8 imports d6 desktop', initScript: authInit, log, session: desktop, fixtureServer, viewport: { name: 'desktop', width: 1440, height: 1000 } }))
        await runWorkflow('imports-d6-mobile', () => assertImportsD6Flow({ appOrigin: defaultOnApp.origin, context: 'd8 imports d6 mobile', initScript: authInit, log, session: mobile, fixtureServer, viewport: { name: 'mobile', width: 390, height: 844 } }))

        // Settings family: exclusive owner of the settings payloads.
        await swapFixtureServer({ settingsAccountFlow: true })
        await runWorkflow('settings-account-desktop', async () => {
          await runRoute({ appOrigin: defaultOnApp.origin, authenticated: true, route: routes.find((route) => route.path === '/profile/settings'), session: desktop, viewport: { name: 'desktop', width: 1440, height: 1000, zoom: 1 }, log })
          await assertSettingsAccountFlow({ appOrigin: defaultOnApp.origin, context: 'd8 settings account desktop', initScript: authInit, log, session: desktop, fixtureServer, viewport: { name: 'desktop', width: 1440, height: 1000 } })
        })
        workflowSessionRef = mobile
        await runWorkflow('settings-account-mobile', async () => {
          await runRoute({ appOrigin: defaultOnApp.origin, authenticated: true, route: routes.find((route) => route.path === '/profile/settings'), session: mobile, viewport: { name: 'mobile', width: 390, height: 844, zoom: 1 }, log })
          await assertSettingsAccountFlow({ appOrigin: defaultOnApp.origin, context: 'd8 settings account mobile', initScript: authInit, log, session: mobile, fixtureServer, viewport: { name: 'mobile', width: 390, height: 844 } })
        })

        // Dialog delivery + mobile page controls: base fixtures.
        await swapFixtureServer({})
        workflowSessionRef = desktop
        for (const route of dialogRoutes) {
          await runWorkflow(`dialogs-desktop ${route}`, async () => {
            await runRoute({ appOrigin: defaultOnApp.origin, authenticated: true, route: routes.find((entry) => entry.path === route), session: desktop, viewport: { name: 'desktop', width: 1440, height: 1000, zoom: 1 }, log })
            await assertDialogDeliveryFlow({ context: `d8 dialogs desktop ${route}`, initScript: authInit, log, session: desktop, route: routes.find((entry) => entry.path === route) })
          })
          await runWorkflow(`dialogs-keyboard-desktop ${route}`, async () => {
            await runRoute({ appOrigin: defaultOnApp.origin, authenticated: true, route: routes.find((entry) => entry.path === route), session: desktop, viewport: { name: 'desktop', width: 1440, height: 1000, zoom: 1 }, log })
            await assertD8DialogKeyboardFlow({ run: (args) => runAgentBrowser({ args, context: `d8 dialogs keyboard ${route}`, initScript: authInit, log, session: desktop }), route })
          })
        }
        workflowSessionRef = mobile
        for (const route of dialogRoutes) {
          await runWorkflow(`dialogs-mobile ${route}`, async () => {
            await runRoute({ appOrigin: defaultOnApp.origin, authenticated: true, route: routes.find((entry) => entry.path === route), session: mobile, viewport: { name: 'mobile', width: 390, height: 844, zoom: 1 }, log })
            await assertDialogDeliveryFlow({ context: `d8 dialogs mobile ${route}`, initScript: authInit, log, session: mobile, route: routes.find((entry) => entry.path === route) })
          })
        }
        await runWorkflow('mobile-page-controls', () => assertMobilePageControlsFlow({ appOrigin: defaultOnApp.origin, context: 'd8 mobile page controls', initScript: authInit, log, session: mobile }))
        await closeSession(desktop, authInit)
        sessions.delete(desktop)
        await closeSession(mobile, authInit)
        sessions.delete(mobile)
        workflowSessionRef = null

        // Chart family: the chart flows plus the D7 security-detail envelopes,
        // everything else off — the committed context (all-selection) matches
        // the chart envelopes.
        await swapFixtureServer({ chartsC2Flow: true, chartsC3Flow: true, chartsC4Flow: true, brokersSecurityD7Flow: true })
        const charts = await launchSession('d8-charts', { origin: defaultOnApp.origin, authenticated: true, viewport: { width: 1440, height: 1000 }, initScript: authInit })
        const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: 'd8 charts cdp', initScript: authInit, log, session: charts })
        const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
        const chartsRun = (args) => runAgentBrowser({ args, context: 'd8 charts', initScript: authInit, log, session: charts })
        await runWorkflow('chart-acceptance', () => assertD8ChartAcceptance({ appOrigin: defaultOnApp.origin, fixtureServer, frontendRoot, run: chartsRun, cdpUrl, initScript: authInit, log, session: charts, captures }))
        await closeSession(charts, authInit)
        sessions.delete(charts)
      }

      // --- Phase D: rendered states on the default-on artifact -----------------
      // Pristine d5-states server; the state machine drives the state changes.
      await swapFixtureServer({ d5States: true })
      // The shared fixture server owns the d5 state machine; phase D switches
      // it and ALWAYS restores 'populated' so the rollback phase sees clean
      // base fixtures.
      try {
        const states = await launchSession('d8-states', { origin: defaultOnApp.origin, authenticated: true, viewport: { width: 1440, height: 1000 }, initScript: authInit })
        const statesRun = (args) => runAgentBrowser({ args, context: 'd8 states', initScript: authInit, log, session: states })
        try {
          await assertD8RenderedStates({ appOrigin: defaultOnApp.origin, fixtureServer, frontendRoot, run: statesRun, captures })
          matrixRows.push({ matrix: 'default-on', workflow: 'rendered-states-subset', result: 'pass' })
          console.log('D8-DEFAULT-ON PASS rendered states (empty/error/filtered-empty subset)')
        } catch (error) {
          matrixRows.push({ matrix: 'default-on', workflow: 'rendered-states-subset', result: 'fail', error: error.message })
          routeFailures.push({ matrix: 'default-on', workflow: 'rendered-states-subset', error: error.message })
          console.error(`D8-DEFAULT-ON FAIL rendered states: ${error.message}`)
        }
        await closeSession(states, authInit)
        sessions.delete(states)
      } finally {
        fixtureServer.setD5State('populated')
      }

      // --- Phase E: rollback spot matrix (kept deliberately separate) ----------
      await swapFixtureServer({})
      try {
        const rollback = await launchSession('d8-rollback', { origin: rollbackApp.origin, authenticated: true, viewport: { width: 1440, height: 1000 }, initScript: authInit })  // pre-built above

        const rRun = (args) => runAgentBrowser({ args, context: 'd8 rollback', initScript: authInit, log, session: rollback })

        const rollbackRow = async (name, fn) => {
          try {
            await fn()
            matrixRows.push({ matrix: 'rollback', route: name, result: 'pass' })
            console.log(`D8-ROLLBACK PASS ${name}`)
          } catch (error) {
            matrixRows.push({ matrix: 'rollback', route: name, result: 'fail', error: error.message })
            routeFailures.push({ matrix: 'rollback', route: name, error: error.message })
            console.error(`D8-ROLLBACK FAIL ${name}: ${error.message}`)
          }
        }

        await rollbackRow('/dashboard', async () => {
          await rRun(['open', `${rollbackApp.origin}/dashboard`])
          await waitFor(rRun, `[...document.querySelectorAll('[data-testid^="allocation-"][data-testid$="-card"] canvas')].length === 3 && !document.querySelector('[data-testid="allocation-legend"]')`)
          const state = await evalProbe(rRun, DASHBOARD_MODERN_STATE)
          assert.equal(state.navPilot, false, 'rollback: the incumbent NAV chart renders, no pilot')
          assert.equal(state.legends, 0, 'rollback: no modern allocation legends')
          const graph = String(await evalProbe(rRun, LOADED_MODULE_GRAPH))
          assert.equal(ECHARTS_RUNTIME.test(graph), false, 'rollback: dashboard loads no ECharts runtime')
          assert.equal(CHARTJS_RUNTIME.test(graph), true, 'rollback: incumbent charts are the lazy Chart.js leaves')
          await rRun(['eval', `(() => { document.querySelector('[data-testid^="allocation-"][data-testid$="-card"]').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
          await rRun(['wait', '150'])
          await rRun(['screenshot', resolve(assetsDir, 'd8-rollback-dashboard.png')])
          captures.push('d8-rollback-dashboard.png')
        })

        await rollbackRow('/database/securities/1', async () => {
          await rRun(['open', `${rollbackApp.origin}/database/securities/1`])
          await waitFor(rRun, `document.querySelectorAll('canvas').length >= 2 && document.querySelectorAll('[data-testid="security-data-table"]').length === 0`)
          const graph = String(await evalProbe(rRun, LOADED_MODULE_GRAPH))
          assert.equal(ECHARTS_RUNTIME.test(graph), false, 'rollback: security page loads no ECharts runtime')
          await rRun(['eval', `(() => { document.querySelector('#security-price-history, .v-main').scrollIntoView({ block: 'start' }); window.scrollBy(0, -200); return true })()`])
          await rRun(['wait', '150'])
          await rRun(['screenshot', resolve(assetsDir, 'd8-rollback-security.png')])
          captures.push('d8-rollback-security.png')
        })

        await rollbackRow('/transactions', async () => {
          await runRoute({ appOrigin: rollbackApp.origin, authenticated: true, route: routes.find((route) => route.path === '/transactions'), session: rollback, viewport: { name: 'rollback-desktop', width: 1440, height: 1000, zoom: 1 }, log })
        })

        await closeSession(rollback, authInit)
        sessions.delete(rollback)
      } finally {
        await rollbackApp.close().catch(() => undefined)
      }
      } finally {
        if (defaultOnApp) await defaultOnApp.close().catch(() => undefined)
        if (rollbackApp) await rollbackApp.close().catch(() => undefined)
        if (fixtureServer) await fixtureServer.close().catch(() => undefined)
      }
    },
    cleanup: () =>
      cleanupBrowserHarness({
        sessions,
        closeSession,
        // The shared fixture/default-on app servers live across all phases and
        // are closed by the harness cleanup on every exit path; the rollback
        // app server is closed at the end of phase E.
        closeAppServer: async () => {
          if (defaultOnApp) await defaultOnApp.close().catch(() => undefined)
        },
        closeFixtureServer: async () => {
          if (fixtureServer) {
            harvestUnmatched(fixtureServer)
            await fixtureServer.close().catch(() => undefined)
          }
        },
        recordError: log,
      }),
    })
  } finally {
    clearInterval(settleWatchdog)
  }

  // Apply the mismatch gate BEFORE the summary is created, so the saved
  // failure list and the exit result can never disagree.
  const mismatchCount = applyFixtureMismatchFailures(routeFailures, fixtureMismatches)
  if (mismatchCount > 0) {
    console.error(`D8 FAIL fixture mismatches: ${mismatchCount} unmatched request(s)`)
  }

  const captureRegistry = await registerPngCaptures(assetsDir)
  const summary = {
    case: 'final-qa-d8',
    matrices: {
      defaultOn: {
        routeProbes: matrixRows.filter((row) => row.matrix === 'default-on' && row.viewport).length,
        longNameProbes: matrixRows.filter((row) => row.matrix === 'default-on-longnames').length,
        workflows: workflowResults.length,
        failures: routeFailures.filter((row) => row.matrix !== 'rollback'),
      },
      rollback: {
        note: 'spot checks here; the FULL rollback route matrix is the standard run-smoke run (its base artifact is built with all-false flags) and stays the rollback acceptance evidence',
        spotChecks: matrixRows.filter((row) => row.matrix === 'rollback').length,
        failures: routeFailures.filter((row) => row.matrix === 'rollback'),
      },
    },
    workflows: workflowResults,
    routeFailures,
    fixtureMismatches,
    delivery,
    artifacts: {
      defaultOn: artifactRecordsRef && { flags: artifactRecordsRef.defaultOn.flags, sha256: artifactRecordsRef.defaultOn.hash.sha256, files: artifactRecordsRef.defaultOn.hash.files, bytes: artifactRecordsRef.defaultOn.hash.bytes },
      rollback: artifactRecordsRef && { flags: artifactRecordsRef.rollback.flags, sha256: artifactRecordsRef.rollback.hash.sha256, files: artifactRecordsRef.rollback.hash.files, bytes: artifactRecordsRef.rollback.hash.bytes },
      envFlagKeysFound: artifactRecordsRef ? artifactRecordsRef.envScan.flagKeysFound : null,
    },
    captures: captureRegistry,
  }
  await writeFile(resolve(artifactsDir, 'final-qa-d8-summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
  await writeFile(resolve(artifactsDir, 'final-qa-d8-delivery.json'), `${JSON.stringify(delivery, null, 2)}\n`)
  console.log(JSON.stringify({
    defaultOnProbes: summary.matrices.defaultOn.routeProbes,
    defaultOnWorkflows: summary.matrices.defaultOn.workflows,
    rollbackSpotChecks: summary.matrices.rollback.spotChecks,
    failures: routeFailures.length,
    captures: captureRegistry.length,
    dashboardGzip: delivery?.dashboard?.gzip ?? null,
  }, null, 2))

  if (routeFailures.length > 0 || mismatchCount > 0) {
    process.exitCode = 1
  }
}
