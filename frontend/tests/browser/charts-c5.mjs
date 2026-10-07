import assert from 'node:assert/strict'
import { resolve } from 'node:path'

import { build } from 'vite'

import { runAgentBrowser } from './protocol.mjs'
import { startBuiltAppServer } from './serve-app.mjs'

// C5a rendered acceptance. Phase A (task 1 — lazy legacy fallback): on a
// clean all-modern v2 dashboard, NO Chart.js runtime module is loaded; the
// user-chosen NAV fallback downloads the legacy leaf lazily, renders the
// SAME accepted response with zero additional API calls, and does not touch
// the allocation family's policy or requests. Phase B (task 2 — deterministic
// release policy): rendered independence across flag artifacts — the NAV-only
// release stage, the explicit all-on candidate, the no-flags release
// candidate and the explicit all-off rollback. Later phases extend this case
// to the combined candidate acceptance and measured delivery.

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
  for (const [key, value] of Object.entries(flags)) process.env[key] = value
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
async function phaseBPolicyMatrix({ appOrigin, candidateServer, navOnlyServer, fixtureServer, run }) {
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

  // Explicit all-on candidate (same behavior as the reviewed default).
  await openDashboardModern(run, candidateServer.origin)
  state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot && state.legends === 3 && state.allocationCanvases === 3, true, 'all-on candidate: three pies plus the NAV pilot')
  await openSecurityModern(run, candidateServer.origin)

  // The no-flags build IS the release candidate: identical rendering without
  // any flag supplied.
  await openDashboardModern(run, candidateServer.origin)
  state = await evalProbe(run, DASHBOARD_MODERN_STATE)
  assert.equal(state.navPilot && state.legends === 3 && state.allocationCanvases === 3, true, 'no-flags candidate: three pies plus the NAV pilot')
  await openSecurityModern(run, candidateServer.origin)

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
  const candidateServer = await startBuiltAppServer(candidateDir)
  const navOnlyServer = await startBuiltAppServer(navOnlyDir)
  const session = `c5-candidate-${process.pid}`
  registerSession(session)
  const initScript = resolve(frontendRoot, 'tests/browser/auth-init.js')
  const run = (args) => runAgentBrowser({ args, context: 'charts c5 candidate', initScript, log, session })

  try {
    await phaseALaziness({ candidateServer, fixtureServer, run })
    await phaseBPolicyMatrix({ appOrigin, candidateServer, navOnlyServer, fixtureServer, run })
    void flagOffRoot
  } finally {
    await candidateServer.close().catch(() => undefined)
    await navOnlyServer.close().catch(() => undefined)
  }
}
