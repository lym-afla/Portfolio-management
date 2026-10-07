import assert from 'node:assert/strict'
import { resolve } from 'node:path'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'

// C5a rendered acceptance. Phase A (task 1 — lazy legacy fallback): on a
// clean all-modern v2 dashboard, NO Chart.js runtime module is loaded; the
// user-chosen NAV fallback downloads the legacy leaf lazily, renders the
// SAME accepted response with zero additional API calls, and does not touch
// the allocation family's policy or requests. Later phases extend this case
// to the combined candidate acceptance and measured delivery.

const NAV_PATH = '/dashboard/api/get-nav-chart-data/'
const BREAKDOWN_PATH = '/dashboard/api/get-breakdown/'

// Any Chart.js runtime module inside a loaded asset's module graph.
const CHARTJS_RUNTIME = /(node_modules\/chart\.js\/|node_modules\/vue-chartjs\/|node_modules\/chartjs-plugin-datalabels\/|node_modules\/chartjs-adapter-date-fns\/)/i

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

const navRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === NAV_PATH).length

const breakdownRequestCount = (fixtureServer) =>
  fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === BREAKDOWN_PATH).length

export async function runChartsC5LazinessFlow({
  frontendRoot,
  fixtureServer,
  log,
  registerSession,
  artifactsDir,
}) {
  const candidateDir = resolve(artifactsDir, 'app-c5-candidate')
  const previous = {
    nav: process.env.VITE_NAV_ECHARTS_ENABLED,
    allocation: process.env.VITE_ALLOCATION_ECHARTS_ENABLED,
    security: process.env.VITE_SECURITY_ECHARTS_ENABLED,
  }
  process.env.VITE_NAV_ECHARTS_ENABLED = 'true'
  process.env.VITE_ALLOCATION_ECHARTS_ENABLED = 'true'
  process.env.VITE_SECURITY_ECHARTS_ENABLED = 'true'
  try {
    await build({ mode: 'browser-test', root: frontendRoot, build: { emptyOutDir: true, outDir: candidateDir } })
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
  const candidateServer = await startBuiltAppServer(candidateDir)
  const session = `c5-candidate-${process.pid}`
  registerSession(session)
  const initScript = resolve(frontendRoot, 'tests/browser/auth-init.js')
  const run = (args) => runAgentBrowser({ args, context: 'charts c5 candidate', initScript, log, session })

  try {
    // --- clean all-modern v2 dashboard: no Chart.js runtime loaded ---------
    await run(['open', `${candidateServer.origin}/dashboard`])
    await waitFor(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length === 3 && !!document.querySelector('[data-testid="nav-echarts-pilot"] canvas')`)
    await run(['wait', '--load', 'networkidle'])
    const graphBefore = String(await evalProbe(run, LOADED_MODULE_GRAPH))
    assert.equal(
      CHARTJS_RUNTIME.test(graphBefore),
      false,
      'all-modern dashboard must load no Chart.js runtime module (found chart.js modules in the loaded graph)',
    )
    assert.ok(/echarts/i.test(graphBefore), 'the modern dashboard still loads the ECharts runtime')

    // --- user-chosen NAV fallback: lazy legacy leaf, same response ---------
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

    const graphAfter = String(await evalProbe(run, LOADED_MODULE_GRAPH))
    assert.equal(
      CHARTJS_RUNTIME.test(graphAfter),
      true,
      'invoking the fallback must lazily download the Chart.js runtime',
    )

    // --- mixed families: the NAV fallback must not touch allocations -------
    const allocationLegends = await evalProbe(run, `document.querySelectorAll('[data-testid="allocation-legend"]').length`)
    assert.equal(allocationLegends, 3, 'allocation family stays modern after the NAV fallback')
    assert.equal(breakdownRequestCount(fixtureServer) - breakdownBefore, 0, 'NAV fallback triggers no allocation refetch')
    fixtureServer.charts.scenario = 'v2'

    console.log('PASS charts-c5 laziness (modern graph chartjs-free; fallback lazy, same response, no refetch)')
  } finally {
    await candidateServer.close().catch(() => undefined)
  }
}
