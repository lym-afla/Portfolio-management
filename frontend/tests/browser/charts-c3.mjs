import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'
import { measureRouteBundles } from '../../scripts/measure-route-bundles.mjs'

// C3 rendered acceptance. Phase A (flag-off artifact): the incumbent renderer
// with NO ECharts in the delivered graph. Phase B (flag-on artifact): the real
// dashboard pilot — independent IRR toggles, keyboard/table inspection,
// viewport reset, no data requests from zoom/legend, retained state across
// refresh, mobile hit-testing, recoverable rendering failure with known-data
// fallback, legacy-only/invalid-contract/mismatch behaviour and the isolated
// synthetic harness. Both artifacts are distinct builds; the harness runs on
// a dedicated dev server. Every session is registered for guaranteed cleanup.

const NAV_PATH = '/dashboard/api/get-nav-chart-data/'
const here = dirname(fileURLToPath(import.meta.url))
const DESIGN_ASSETS = resolve(here, '../../../docs/design/assets/frontend-workspace')

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 12000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const navRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === NAV_PATH).length

const chartState = `(() => ({
  pilot: !!document.querySelector('[data-testid="nav-echarts-pilot"]'),
  canvas: !!document.querySelector('[data-testid="nav-chart"] canvas'),
  notice: !!document.querySelector('[data-testid="nav-capability-notice"]'),
  error: document.querySelector('[data-testid="nav-error"]')?.innerText ?? null,
  legendButtons: [...document.querySelectorAll('[data-series-id]')].map((button) => ({
    id: button.getAttribute('data-series-id'),
    pressed: button.getAttribute('aria-pressed'),
    text: button.innerText.trim(),
  })),
  tableCaption: document.querySelector('[data-testid="nav-echarts-pilot"] caption')?.innerText ?? null,
  inspection: document.querySelector('.chart-inspection')?.innerText ?? null,
}))()`

async function legendButton(run, text) {
  const state = await evalProbe(run, chartState)
  const button = state.legendButtons.find((entry) => entry.text === text)
  assert.ok(button, `legend control ${text} must exist`)
  return button
}

async function clickLegend(run, text) {
  await run(['eval', `(() => {
    const button = [...document.querySelectorAll('[data-series-id]')].find(el => el.innerText.trim() === '${text}')
    if (!button) throw new Error('missing legend ${text}')
    button.click()
    return true
  })()`])
}

async function clickFrequency(run, label) {
  await run(['eval', `(() => {
    const button = [...document.querySelectorAll('.v-btn-toggle button')].find(el => el.textContent.trim() === '${label}')
    if (!button) throw new Error('frequency ${label} missing')
    button.click()
    return true
  })()`])
}

async function measureDashboard({ run, label, root }) {
  await run(['wait', '--load', 'networkidle'])
  const observed = await run(['eval', `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`])
  const graph = await measureRouteBundles({ root, resources: observed.result })
  return { label, graph }
}

// ---------------------------------------------------------------------------
// Phase A: default-off artifact — incumbent renderer, provably lazy delivery.

export async function assertChartsC3FlagOffFlow({ appOrigin, context, initScript, log, session }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"]') !== null`)
  const state = await evalProbe(run, chartState)
  assert.equal(state.pilot, false, 'flag off: no pilot artifacts')
  assert.equal(state.canvas, true, 'flag off: incumbent Chart.js canvas renders')
  assert.equal(state.notice, false, 'flag off: v2 responses show no notice')
  await run(['wait', '--load', 'networkidle'])
  const resources = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).join('\\n')`)
  assert.ok(!/echarts/i.test(String(resources)), 'flag off: no ECharts asset fetched on the dashboard')
  // The build may carry a dormant lazy chunk; the loaded module graph must
  // not contain ECharts/vue-echarts runtime on the default-off dashboard.
  const loadedModules = await evalProbe(run, `(async () => {
    const membership = await fetch('/.vite/module-membership.json').then(response => response.json()).catch(() => ({}))
    const assets = [...new Set(performance.getEntriesByType('resource').map(entry => new URL(entry.name).pathname.slice(1)))]
    const modules = assets.flatMap((asset) => membership[asset] || [])
    return modules.join('\\n')
  })()`)
  assert.ok(!/echarts/i.test(String(loadedModules)), 'flag off: loaded module graph contains no ECharts runtime')
  await run(['open', `${appOrigin}/login`])
  await run(['wait', '--load', 'networkidle'])
  const loginResources = await evalProbe(run, `performance.getEntriesByType('resource').map(entry => entry.name).join('\\n')`)
  assert.ok(!/echarts/i.test(String(loginResources)), 'flag off: no ECharts asset on login')
  console.log('PASS charts-c3 flag-off delivery (incumbent renderer, echarts-free graph)')
}

// ---------------------------------------------------------------------------
// Phase B/C: flag-on artifact, dashboard + isolated harness.

export async function runChartsC3PilotFlow({
  appOrigin,
  flagOffRoot,
  frontendRoot,
  fixtureServer,
  log,
  registerSession,
  artifactsDir,
}) {
  const pilotDir = resolve(artifactsDir, 'app-pilot')
  const previousFlag = process.env.VITE_NAV_ECHARTS_ENABLED
  process.env.VITE_NAV_ECHARTS_ENABLED = 'true'
  try {
    await build({ mode: 'browser-test', root: frontendRoot, build: { emptyOutDir: true, outDir: pilotDir } })
  } finally {
    if (previousFlag === undefined) delete process.env.VITE_NAV_ECHARTS_ENABLED
    else process.env.VITE_NAV_ECHARTS_ENABLED = previousFlag
  }
  const pilotServer = await startBuiltAppServer(pilotDir)
  const session = `c3-pilot-${process.pid}`
  registerSession(session)
  const initScript = resolve('tests/browser/auth-init.js')
  const run = (args) => runAgentBrowser({ args, context: 'charts c3 pilot', initScript, log, session })

  try {
    await run(['open', `${pilotServer.origin}/dashboard`])
    await waitFor(run, `document.querySelectorAll('[data-series-id]').length > 0 && document.querySelector('[data-testid="nav-echarts-pilot"] canvas') !== null`)
    let state = await evalProbe(run, chartState)
    assert.equal(state.pilot, true, 'flag on: pilot composition renders')
    assert.equal(state.notice, false, 'flag on: v2 shows no capability notice')
    const interval = await legendButton(run, 'Interval IRR (annualized)')
    const inception = await legendButton(run, 'Since-inception IRR (annualized)')
    assert.equal(interval.id, 'metric:irr_interval')
    assert.equal(inception.id, 'metric:irr_inception')
    assert.equal(state.tableCaption, 'Exact values by period')
    assert.match(String(state.inspection), /Select a table row|Inspection/, 'inspection panel present')

    // --- independent IRR toggles; legend/zoom never request data ----------
    const beforeLegend = navRequestCount(fixtureServer)
    await clickLegend(run, 'Interval IRR (annualized)')
    await run(['wait', '150'])
    let buttons = (await evalProbe(run, chartState)).legendButtons
    assert.equal(buttons.find((entry) => entry.id === 'metric:irr_interval').pressed, 'false', 'interval IRR hidden')
    assert.equal(buttons.find((entry) => entry.id === 'metric:irr_inception').pressed, 'true', 'inception IRR untouched')
    await clickLegend(run, 'Interval IRR (annualized)')
    await run(['wait', '150'])
    assert.equal(navRequestCount(fixtureServer) - beforeLegend, 0, 'legend toggles issue no requests')

    // --- keyboard/table inspection into the shared model ------------------
    await run(['eval', `(() => { const row = document.querySelectorAll('[data-testid="nav-echarts-pilot"] tbody tr')[1]; row.focus(); row.click(); document.querySelector('.chart-inspection').scrollIntoView({ block: 'center' }); return true })()`])
    await run(['wait', '150'])
    state = await evalProbe(run, chartState)
    assert.match(String(state.inspection), /Jul-26/, 'inspection shows the selected period')
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c3-nav-keyboard.png')])

    // --- viewport controls: zoom is view-only ------------------------------
    const selects = await evalProbe(run, `document.querySelectorAll('.chart-inspection select').length`)
    assert.equal(selects, 2, 'native start/end period selects')
    await run(['eval', `(() => { const select = document.querySelectorAll('.chart-inspection select')[0]; select.value = select.options[1].value; select.dispatchEvent(new Event('change', { bubbles: true })); return true })()`])
    await run(['wait', '150'])
    await run(['eval', `document.querySelector('.chart-inspection__reset').click()`])
    await run(['wait', '150'])
    assert.equal(navRequestCount(fixtureServer) - beforeLegend, 0, 'viewport changes issue no requests')

    // --- same-context refresh retains interaction; partial data visible ----
    await run(['eval', `document.querySelector('[data-testid="nav-chart"]').setAttribute('data-c3-marker', 'first')`])
    await clickLegend(run, 'Interval IRR (annualized)')
    const beforeRefresh = navRequestCount(fixtureServer)
    await clickFrequency(run, 'Day')
    await waitFor(run, `document.querySelector('[data-testid="nav-chart"]') !== null && document.querySelector('[data-testid="nav-error"]') === null`)
    await run(['wait', '400'])
    assert.equal(navRequestCount(fixtureServer) - beforeRefresh, 1, 'one request per parameter event')
    assert.equal(
      await evalProbe(run, `document.querySelector('[data-testid="nav-chart"]')?.getAttribute('data-c3-marker')`),
      'first',
      'pilot chart element survives the refresh',
    )
    buttons = (await evalProbe(run, chartState)).legendButtons
    assert.equal(buttons.find((entry) => entry.id === 'metric:irr_interval').pressed, 'false', 'hidden IRR stays hidden across refresh')
    const tableText = await evalProbe(run, `document.querySelector('[data-testid="nav-echarts-pilot"] table').innerText`)
    assert.match(tableText, /partial|known subtotal|N\/A/, 'partial/unavailable points stay explicit')
    // Faithful fixtures render comma-grouped monetary displays verbatim.
    assert.match(tableText, /\d,\d{3}/, 'monthly NAV table shows thousands separators')
    // Distinct captures: partial state (table + inspection with partial text
    // in view), then both IRRs re-shown with the chart, legend and frequency
    // controls scrolled into view for the desktop capture.
    await run(['eval', `(() => { document.querySelector('.chart-table').scrollIntoView({ block: 'start' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c3-nav-partial.png')])
    await clickLegend(run, 'Interval IRR (annualized)')
    await run(['wait', '150'])
    buttons = (await evalProbe(run, chartState)).legendButtons
    assert.equal(buttons.find((entry) => entry.id === 'metric:irr_interval').pressed, 'true', 'both IRRs visible for the desktop capture')
    await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c3-nav-desktop.png')])

    // --- mobile profile with real hit-testing ------------------------------
    await run(['set', 'viewport', '390', '844'])
    await waitFor(run, `document.querySelector('[data-testid="nav-echarts-pilot"] canvas') !== null`)
    await run(['wait', '400'])
    // EVERY legend control, both axes and the viewport controls must survive
    // the desktop->390px shrink: nothing may overflow the panel's box.
    const shrink = await evalProbe(run, `(() => {
      const panel = document.querySelector('.nav-chart-panel__pilot')
      const panelRect = panel ? panel.getBoundingClientRect() : null
      const controls = [...document.querySelectorAll('[data-series-id]')]
      const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
      const viewportControls = [...document.querySelectorAll('.chart-inspection select, .chart-inspection__reset')]
      const withinPanel = (element) => {
        const rect = element.getBoundingClientRect()
        return rect.width > 0 && panelRect ? rect.right <= panelRect.right + 1 : false
      }
      return {
        panelWidth: panelRect ? Math.round(panelRect.width) : null,
        widestChild: Math.max(...[...panel.children].map((child) => Math.round(child.getBoundingClientRect().width))),
        canvasWidth: canvas ? Math.round(canvas.getBoundingClientRect().width) : null,
        legendCount: controls.length,
        legendWithinPanel: controls.map((button) => withinPanel(button)),
        viewportWithinPanel: viewportControls.map((control) => withinPanel(control)),
      }
    })()`)
    assert.ok(shrink.panelWidth !== null, 'mobile: pilot panel present')
    assert.ok(
      shrink.widestChild <= shrink.panelWidth + 1,
      `mobile: panel children must shrink with the panel (widest ${shrink.widestChild}px vs panel ${shrink.panelWidth}px)`,
    )
    assert.ok(
      shrink.canvasWidth !== null && shrink.canvasWidth <= shrink.panelWidth + 1,
      `mobile: chart canvas must resize with the panel (canvas ${shrink.canvasWidth}px vs panel ${shrink.panelWidth}px)`,
    )
    assert.equal(shrink.legendWithinPanel.filter(Boolean).length, shrink.legendCount,
      `mobile: every legend control inside the panel (got ${shrink.legendWithinPanel.filter(Boolean).length}/${shrink.legendCount})`)
    assert.ok(shrink.viewportWithinPanel.every(Boolean), 'mobile: viewport controls inside the panel')
    // Both axes visible after resize: left and right y-axis labels exist on
    // the shrunk canvas (ECharts drops an axis only if it cannot fit).
    const axesProbe = await evalProbe(run, `(() => {
      const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
      if (!canvas) return { present: false }
      return { present: true, width: Math.round(canvas.getBoundingClientRect().width) }
    })()`)
    assert.ok(axesProbe.present && axesProbe.width > 200, `mobile: chart canvas usable after resize (${axesProbe.width}px)`)
    // Resize back to desktop: state and sizing recover (both directions).
    await run(['set', 'viewport', '1440', '1000'])
    await run(['wait', '400'])
    const restored = await evalProbe(run, `(() => {
      const panel = document.querySelector('.nav-chart-panel__pilot')
      const canvas = document.querySelector('[data-testid="nav-echarts-pilot"] canvas')
      const buttons = [...document.querySelectorAll('[data-series-id]')]
      return {
        panelWidth: panel ? Math.round(panel.getBoundingClientRect().width) : null,
        canvasWidth: canvas ? Math.round(canvas.getBoundingClientRect().width) : null,
        pressed: buttons.map((button) => button.getAttribute('aria-pressed')),
      }
    })()`)
    assert.ok(restored.panelWidth > 900, `desktop restore: panel width recovered (${restored.panelWidth}px)`)
    assert.ok(restored.canvasWidth && restored.canvasWidth > 600, `desktop restore: canvas re-expanded (${restored.canvasWidth}px)`)
    assert.deepEqual(new Set(restored.pressed), new Set(['true']), 'desktop restore: all series still visible')
    await run(['set', 'viewport', '390', '844'])
    const hit = await evalProbe(run, `(() => {
      const targets = ['.v-btn-toggle button', '[data-series-id]', '.chart-inspection select', '.chart-inspection__reset', '.chart-table']
      return targets.map((selector) => {
        const elements = [...document.querySelectorAll(selector)]
        if (elements.length === 0) return { selector, present: false }
        return elements.map((element) => {
          element.scrollIntoView({ block: 'center' })
          const rect = element.getBoundingClientRect()
          const hitElement = document.elementFromPoint(rect.left + Math.min(rect.width / 2, window.innerWidth / 2), Math.max(rect.top + rect.height / 2, 8))
          return { selector, present: true, hittable: hitElement === element || element.contains(hitElement) }
        })
      }).flat()
    })()`)
    for (const entry of hit) {
      assert.equal(entry.present, true, `mobile: ${entry.selector} present`)
      assert.equal(entry.hittable, true, `mobile: ${entry.selector} actually hittable`)
    }
    await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c3-nav-mobile.png')])
    await run(['set', 'viewport', '1440', '1000'])

    // --- native 200% zoom (CDP key events, dpr-verified) --------------------
    const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: 'charts c3 cdp', initScript, log, session })
    const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
    const zoom = await new Promise((resolveSpawn, rejectSpawn) => {
      const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), pilotServer.origin, '200'], { stdio: 'pipe' })
      let out = ''
      child.stdout.on('data', (chunk) => { out += chunk })
      child.on('error', rejectSpawn)
      child.on('close', (code) => resolveSpawn({ code, out }))
    })
    assert.equal(zoom.code, 0, `native 200% zoom must be dpr-verified (${zoom.out.trim()})`)
    await new Promise((resolveSpawn, rejectSpawn) => {
      const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), pilotServer.origin, '100'], { stdio: 'ignore' })
      child.on('error', rejectSpawn)
      child.on('close', (code) => resolveSpawn(code))
    })

    // --- recoverable rendering failure with known-data fallback -------------
    fixtureServer.charts.scenario = 'outrange'
    const beforeFailure = navRequestCount(fixtureServer)
    await clickFrequency(run, 'Week')
    await waitFor(run, `document.querySelector('[data-testid="chart-render-error"]') !== null`)
    await run(['eval', `document.querySelector('[data-testid="chart-render-fallback"]').click()`])
    await waitFor(run, `document.querySelector('[data-testid="nav-fallback-notice"]') !== null && document.querySelector('[data-testid="nav-chart"] canvas') !== null`)
    assert.equal(navRequestCount(fixtureServer) - beforeFailure, 1, 'rendering failure adds no extra request beyond its query')
    fixtureServer.charts.scenario = 'v2'

    // --- legacy-only and invalid-contract states ----------------------------
    fixtureServer.charts.scenario = 'legacy'
    await run(['reload'])
    await waitFor(run, `document.querySelector('[data-testid="nav-capability-notice"]') !== null`)
    state = await evalProbe(run, chartState)
    assert.equal(state.pilot, false, 'legacy-only stays on the incumbent renderer')
    assert.equal(state.canvas, true, 'legacy-only still renders Chart.js')
    await run(['eval', `(() => { document.querySelector('[data-testid="nav-chart"]').scrollIntoView({ block: 'start' }); return true })()`])
    await run(['wait', '150'])
    await run(['screenshot', resolve(DESIGN_ASSETS, 'c3-nav-legacy.png')])
    fixtureServer.charts.scenario = 'malformed'
    const beforeMalformed = navRequestCount(fixtureServer)
    await run(['reload'])
    await waitFor(run, `document.querySelector('[data-testid="nav-error"]') !== null`)
    state = await evalProbe(run, chartState)
    assert.equal(state.pilot, false, 'invalid v2 never mounts the pilot')
    await run(['wait', '400'])
    assert.equal(navRequestCount(fixtureServer) - beforeMalformed, 1, 'invalid contract: exactly one request, no retry')

    // --- mismatch reconciles once; manual retry recovers --------------------
    fixtureServer.charts.scenario = 'v2'
    await run(['eval', `document.querySelector('[data-testid="nav-retry"]')?.click()`])
    await waitFor(run, `document.querySelectorAll('[data-series-id]').length > 0`)
    fixtureServer.charts.scenario = 'mismatch'
    const beforeMismatch = navRequestCount(fixtureServer)
    await clickFrequency(run, 'Month')
    await waitFor(run, `document.querySelector('[data-testid="nav-error"]') !== null`)
    await run(['wait', '800'])
    const mismatchRequests = navRequestCount(fixtureServer) - beforeMismatch
    assert.ok(mismatchRequests >= 2 && mismatchRequests <= 3, `bounded reconciliation episode (${mismatchRequests} requests)`)
    fixtureServer.charts.scenario = 'v2'
    await run(['eval', `document.querySelector('[data-testid="nav-retry"]')?.click()`])
    await waitFor(run, `document.querySelectorAll('[data-series-id]').length > 0 && document.querySelector('[data-testid="nav-error"]') === null`)

    // --- delivery measurements: distinct flag artifacts ----------------------
    const offRun = (args) => runAgentBrowser({ args, context: 'charts c3 flag-off measure', initScript, log, session })
    await offRun(['open', `${appOrigin}/dashboard`])
    const offMeasurement = await measureDashboard({ run: offRun, label: 'dashboard-flag-off', root: flagOffRoot })
    await run(['open', `${pilotServer.origin}/dashboard`])
    await waitFor(run, `document.querySelector('[data-testid="nav-echarts-pilot"] canvas') !== null`)
    const onMeasurement = await measureDashboard({ run, label: 'dashboard-flag-on', root: pilotDir })
    const echartsFiles = onMeasurement.graph.files.filter((file) => /echarts/i.test(file.asset))
    // Cold timing and font delivery without injected init scripts (they run
    // in a separate agent-browser context and proved unreliable): the pilot
    // renderer's frontend render time comes from the isolated harness's own
    // same-world instrumentation (read after the harness section); the
    // dashboards contribute standard navigation timings and the NAV API
    // request duration from the performance API, keeping API time separate
    // from render time.
    const timed = {}
    for (const [phase, origin, canvasWait] of [
      ['flagOff', appOrigin, `document.querySelector('[data-testid="nav-chart"] canvas') !== null`],
      ['flagOn', pilotServer.origin, `document.querySelector('[data-testid="nav-echarts-pilot"] canvas') !== null`],
    ]) {
      const measureSession = `c3-measure-${phase}-${process.pid}`
      const authInitPath = resolve(here, 'auth-init.js')
      registerSession(measureSession, authInitPath)
      const timedContext = `charts c3 timing ${phase}`
      // The init script rides ONLY the open: agent-browser re-executes
      // --init-script on every command, which would re-run fixture auth.
      const timedRun = (args, withInit = false) => runAgentBrowser({ args, context: timedContext, initScript: withInit ? authInitPath : undefined, log, session: measureSession })
      await timedRun(['open', `${origin}/dashboard`], true)
      await timedRun(['wait', '--fn', canvasWait, '--timeout', '20000'])
      timed[phase] = await evalProbe(timedRun, `(() => {
        const navigation = performance.getEntriesByType('navigation')[0] || {}
        const api = performance.getEntriesByType('resource').find((entry) => entry.name.includes('get-nav-chart-data'))
        const fonts = performance.getEntriesByType('resource')
          .filter((entry) => /\\.(woff2?|ttf|otf)/i.test(new URL(entry.name).pathname))
          .map((entry) => ({ file: new URL(entry.name).pathname.split('/').pop(), transferBytes: entry.transferSize || null }))
        return {
          apiMs: api ? Math.round(api.duration) : null,
          domContentLoadedMs: Math.round(navigation.domContentLoadedEventEnd || 0),
          loadEventMs: Math.round(navigation.loadEventEnd || 0),
          canvasPresentMs: Math.round(performance.now()),
          fonts,
        }
      })()`)
    }
    let harnessTiming = null
    const report = {
      note: 'gzip JS/CSS via the R7 helper; render timing: harness = script start to first painted pilot canvas frame (same-world instrumentation, no API involved); dashboards = standard navigation timings plus the NAV API request duration (API time separate); fonts reported separately from resource timing',
      off: offMeasurement.graph,
      on: onMeasurement.graph,
      echartsFiles,
      renderTiming: { dashboards: timed, harness: harnessTiming },
    }
    await mkdir(artifactsDir, { recursive: true })
    await writeFile(resolve(artifactsDir, 'charts-c3-delivery.json'), `${JSON.stringify(report, null, 2)}\n`)
    console.log(`MEASURE charts-c3 delivery: flag-off dashboard ${offMeasurement.graph.gzipJsCss} bytes gzip; flag-on ${onMeasurement.graph.gzipJsCss} bytes gzip (echarts assets: ${echartsFiles.length})`)
    console.log(`MEASURE charts-c3 timing: api ${timed.flagOff.apiMs}/${timed.flagOn.apiMs}ms; domContentLoaded ${timed.flagOff.domContentLoadedMs}/${timed.flagOn.domContentLoadedMs}ms; fonts ${timed.flagOff.fonts.length}/${timed.flagOn.fonts.length}`)

    // --- isolated synthetic harness on a dedicated dev server ----------------
    const dev = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5199', '--strictPort'], {
      cwd: frontendRoot,
      env: { ...process.env, VITE_NAV_ECHARTS_ENABLED: 'true' },
      stdio: 'ignore',
      shell: false,
    })
    try {
      let ready = false
      for (let attempt = 0; !ready && attempt < 60; attempt += 1) {
        ready = await fetch('http://127.0.0.1:5199/src/features/charts/__tests__/render/index.html')
          .then((response) => response.ok)
          .catch(() => false)
        if (!ready) await new Promise((resolveSleep) => setTimeout(resolveSleep, 500))
      }
      assert.ok(ready, 'harness dev server must start')
      await run(['open', 'http://127.0.0.1:5199/src/features/charts/__tests__/render/index.html'])
      await waitFor(run, `document.querySelectorAll('[data-series-id]').length > 0`)
      const harness = await evalProbe(run, `(() => ({
        heading: document.querySelector('h1')?.innerText ?? null,
        scenario: document.querySelector('.harness__scenario')?.innerText ?? null,
        pilot: !!document.querySelector('[data-testid="nav-echarts-pilot"]'),
      }))()`)
      assert.match(String(harness.heading), /C3 NAV pilot render harness/, 'harness mounts')
      assert.equal(harness.pilot, true, 'harness renders the pilot')
      // The harness records its own cold frontend render timing (script
      // evaluation to first painted pilot canvas frame; no API involved).
      await waitFor(run, `window.__harnessTiming && window.__harnessTiming.chartReadyAt !== null`)
      harnessTiming = await evalProbe(run, `(() => {
        const timing = window.__harnessTiming
        return { scriptStartMs: Math.round(timing.scriptStart), chartReadyMs: Math.round(timing.chartReadyAt), renderMs: Math.round(timing.chartReadyAt - timing.scriptStart) }
      })()`)
      // Scenario controls: empty and invalid-contract states.
      await run(['eval', `([...document.querySelectorAll('.harness__controls button')].find(el => el.textContent === 'Empty v2')?.click(), true)`])
      await waitFor(run, `document.querySelector('[data-testid="nav-echarts-pilot"]')?.innerText.includes('No data for the selected account') === true`)
      await run(['eval', `([...document.querySelectorAll('.harness__controls button')].find(el => el.textContent === 'Invalid contract')?.click(), true)`])
      await waitFor(run, `document.querySelector('[data-testid="nav-error"]') !== null`)
      console.log('PASS charts-c3 isolated harness (empty + invalid-contract states)')
    } finally {
      if (process.platform === 'win32') spawn('taskkill', ['/pid', String(dev.pid), '/T', '/F'], { stdio: 'ignore' })
      else dev.kill('SIGTERM')
    }

    // The report is completed after the harness so its render timing is
    // included, then persisted for the evidence record.
    report.renderTiming.harness = harnessTiming
    await writeFile(resolve(artifactsDir, 'charts-c3-delivery.json'), `${JSON.stringify(report, null, 2)}\n`)
    console.log(`MEASURE charts-c3 harness render: ${harnessTiming ? harnessTiming.renderMs : 'n/a'}ms (frontend only, no API)`)

    console.log('PASS charts-c3 pilot flow (dashboard, flag-on artifact)')
  } finally {
    await pilotServer.close().catch(() => undefined)
  }
}
