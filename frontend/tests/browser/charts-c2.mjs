import assert from 'node:assert/strict'
import { resolve } from 'node:path'

import { runAgentBrowser } from './protocol.mjs'

// C2 rendered acceptance: v2 negotiation with the incumbent Chart.js canvas,
// honest legacy-only capability notice, malformed v2 failing without a legacy
// retry, same-context chart retention, manual retry, context-mismatch
// reconciliation through the existing store, and a stale held response that
// cannot disturb the newer query. Desktop flow plus a mobile pass with a real
// hit-test of the frequency control.

const NAV_PATH = '/dashboard/api/get-nav-chart-data/'

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 10000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const chartState = `(() => ({
  chart: !!document.querySelector('[data-testid="nav-chart"]'),
  canvas: !!document.querySelector('[data-testid="nav-chart"] canvas'),
  notice: !!document.querySelector('[data-testid="nav-capability-notice"]'),
  error: document.querySelector('[data-testid="nav-error"]')?.innerText ?? null,
}))()`

async function clickFrequency(run, label, context) {
  await run(['eval', `(() => {
    const button = [...document.querySelectorAll('.v-btn-toggle button')].find(el => el.textContent.trim() === '${label}')
    if (!button) throw new Error('frequency ${label} missing')
    button.click()
    return true
  })()`])
  void context
}

const navRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === NAV_PATH).length

export async function assertChartsC2Flow({ appOrigin, context, initScript, log, session, fixtureServer }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })

  // --- v2 negotiation with the incumbent renderer -------------------------
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"]') !== null`)
  let state = await evalProbe(run, chartState)
  assert.equal(state.chart, true, `${context}: validated v2 payload keeps the chart mounted`)
  assert.equal(state.canvas, true, `${context}: Chart.js canvas renders`)
  assert.equal(state.notice, false, `${context}: v2 responses show no capability notice`)
  assert.equal(state.error, null, `${context}: no error on clean v2`)

  // --- legacy_only: honest notice, chart still renders ---------------------
  fixtureServer.charts.scenario = 'legacy'
  await run(['reload'])
  await waitFor(run, `document.querySelector('[data-testid="nav-capability-notice"]') !== null`)
  state = await evalProbe(run, chartState)
  assert.equal(state.canvas, true, `${context}: legacy-only still renders Chart.js`)
  assert.equal(state.error, null, `${context}: legacy-only is not an error`)

  // --- malformed v2: explicit error, exactly one request, no downgrade ----
  fixtureServer.charts.scenario = 'malformed'
  const beforeMalformed = navRequestCount(fixtureServer)
  await run(['reload'])
  await waitFor(run, `document.querySelector('[data-testid="nav-error"]') !== null`)
  state = await evalProbe(run, chartState)
  assert.ok(/chartV2|version/i.test(state.error ?? ''), `${context}: malformed v2 surfaces its message`)
  assert.equal(state.notice, false, `${context}: invalid v2 is never a capability notice`)
  await run(['wait', '400'])
  const malformedDelta = navRequestCount(fixtureServer) - beforeMalformed
  assert.equal(malformedDelta, 1, `${context}: no silent legacy retry (observed ${malformedDelta} GETs)`)

  // --- successful manual retry ---------------------------------------------
  fixtureServer.charts.scenario = 'v2'
  await run(['eval', `document.querySelector('[data-testid="nav-retry"]')?.click()`])
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"]') !== null && document.querySelector('[data-testid="nav-error"]') === null`)
  state = await evalProbe(run, chartState)
  assert.equal(state.canvas, true, `${context}: retry restores the chart`)

  // --- same-context parameter change retains the mounted chart -------------
  await run(['eval', `document.querySelector('[data-testid="nav-chart"]').setAttribute('data-c2-marker', 'first')`])
  const beforeFrequency = navRequestCount(fixtureServer)
  await clickFrequency(run, 'Day', context)
  await waitFor(run, `document.querySelectorAll('[data-testid="nav-chart"]').length === 1`)
  await run(['wait', '400'])
  state = await evalProbe(run, chartState)
  assert.equal(navRequestCount(fixtureServer) - beforeFrequency, 1, `${context}: one request per parameter event`)
  assert.equal(
    (await evalProbe(run, `document.querySelector('[data-testid="nav-chart"]')?.getAttribute('data-c2-marker')`)),
    'first',
    `${context}: accepted chart element survives the refresh`,
  )
  assert.equal(state.error, null, `${context}: parameter change stays error-free`)

  // --- current context mismatch reconciles once, then waits for the user ---
  fixtureServer.charts.scenario = 'mismatch'
  const beforeMismatch = navRequestCount(fixtureServer)
  const fixtureBudgetBefore = fixtureServer.requests.length
  await clickFrequency(run, 'Week', context)
  await waitFor(run, `document.querySelector('[data-testid="nav-error"]') !== null`)
  state = await evalProbe(run, chartState)
  assert.match(state.error ?? '', /match/i, `${context}: mismatch names the disagreement`)
  // One reconciliation refetch happens; the still-mismatching response must
  // not start a loop — the error then stays until the user retries.
  await run(['wait', '800'])
  const mismatchRequests = navRequestCount(fixtureServer) - beforeMismatch
  assert.ok(mismatchRequests >= 2, `${context}: reconciliation refresh re-reads the chart`)
  assert.ok(mismatchRequests <= 3, `${context}: no reconciliation retry loop (${mismatchRequests} requests)`)
  assert.ok(fixtureServer.requests.length - fixtureBudgetBefore < 60, `${context}: divergence episode stays bounded`)
  fixtureServer.charts.scenario = 'v2'
  await run(['eval', `document.querySelector('[data-testid="nav-retry"]')?.click()`])
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"] canvas') !== null && document.querySelector('[data-testid="nav-error"]') === null`)

  // --- a stale held response cannot disturb the newer query ----------------
  fixtureServer.charts.scenario = 'hold'
  await clickFrequency(run, 'Month', context)
  for (let attempt = 0; !fixtureServer.heldReads.has(NAV_PATH) && attempt < 20; attempt++) {
    await run(['wait', '100'])
  }
  assert.ok(fixtureServer.heldReads.has(NAV_PATH), `${context}: old chart query is still pending`)
  fixtureServer.charts.scenario = 'v2'
  fixtureServer.charts.releaseWith = 'mismatch'
  await clickFrequency(run, 'Quarter', context)
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"] canvas') !== null && document.querySelector('[data-testid="nav-error"]') === null`)
  const beforeRelease = navRequestCount(fixtureServer)
  fixtureServer.releaseRead(NAV_PATH)
  await run(['wait', '600'])
  state = await evalProbe(run, chartState)
  assert.equal(state.error, null, `${context}: late stale mismatch must not error the newer chart`)
  assert.equal(state.canvas, true, `${context}: newer chart keeps rendering after the stale release`)
  assert.equal(navRequestCount(fixtureServer) - beforeRelease, 0, `${context}: stale release triggers no further request`)

  // --- desktop capture -------------------------------------------------------
  await run(['screenshot', resolve('tests/browser/artifacts/screenshots', 'charts-c2-desktop.png')])

  // --- mobile pass: chart usable, frequency control actually hittable ------
  await run(['set', 'viewport', '390', '844'])
  await waitFor(run, `document.querySelector('[data-testid="nav-chart"] canvas') !== null`)
  const hit = await evalProbe(run, `(() => {
    const button = [...document.querySelectorAll('.v-btn-toggle button')].find(el => el.textContent.trim() === 'Week')
    if (!button) return { found: false }
    const rect = button.getBoundingClientRect()
    const hitElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return { found: true, hittable: hitElement === button || button.contains(hitElement), withinViewport: rect.top >= 0 && rect.left >= 0 && rect.right <= window.innerWidth && rect.bottom <= window.innerHeight }
  })()`)
  assert.equal(hit.found, true, `${context}: mobile frequency control present`)
  assert.equal(hit.hittable, true, `${context}: mobile frequency control is actually hittable`)
  assert.equal(hit.withinViewport, true, `${context}: mobile frequency control within viewport`)
  state = await evalProbe(run, chartState)
  assert.equal(state.canvas, true, `${context}: mobile chart renders`)
  assert.equal(state.notice, false, `${context}: mobile shows no notice for v2`)
  assert.equal(state.error, null, `${context}: mobile stays error-free`)
  await run(['screenshot', resolve('tests/browser/artifacts/screenshots', 'charts-c2-mobile.png')])
  await run(['set', 'viewport', '1440', '1000'])
}
