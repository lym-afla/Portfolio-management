import { rm, mkdir, writeFile, appendFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { build } from 'vite'

import { startFixtureServer } from './fixture-server.mjs'
import { startBuiltAppServer } from './serve-app.mjs'
import { assertChartsC3FlagOffFlow, runChartsC3PilotFlow } from './charts-c3.mjs'
import {
  cleanupBrowserHarness,
  runBrowserHarnessLifecycle,
} from './lifecycle.mjs'
import { runAgentBrowser } from './protocol.mjs'
import { assertFocusedLayoutFlow, assertLayoutGeometry, assertPositionsToolbarFlow } from './layout.mjs'
import { assertContextFailureFlow } from './context.mjs'
import { assertMountedDateFlow } from './dates.mjs'
import { assertRequestOrderFlow } from './requests.mjs'
import { assertDashboardRecoveryFlow } from './recovery.mjs'
import { routes, viewports } from './routes.mjs'
import { measureRouteBundles, assertRouteDelivery } from '../../scripts/measure-route-bundles.mjs'
import { assertDialogDeliveryFlow, assertDialogChunkRecovery, dialogRoutes } from './dialogs.mjs'
import { assertD4TablesFlow, assertD4TransactionsFlow, assertD4ViewportChecks, captureD4Screenshots } from './d4.mjs'
import { assertChartsC2Flow } from './charts-c2.mjs'
import { assertChartsC4FlagOffFlow, runChartsC4PilotFlow } from './charts-c4.mjs'
import { runChartsC5Flow } from './charts-c5.mjs'
import { assertD5FamilyProbesFlow, assertD5NativeZoomFlow, assertD5StatesFlow, assertMobilePageControlsFlow, captureD5Screenshots, d5FamilyRoutes } from './d5.mjs'
import { assertSettingsAccountFlow } from './settings-account.mjs'
import { assertImportsD6Flow } from './imports-d6.mjs'
import { assertBrokersSecurityD7Flow } from './brokers-security-d7.mjs'

const caseIndex = process.argv.indexOf('--case')
const selectedCase = caseIndex < 0 ? null : process.argv[caseIndex + 1]
if (selectedCase !== null && !['layout', 'context', 'dates', 'requests', 'recovery', 'delivery', 'dialogs', 'dialog-recovery', 'd4', 'charts-c2', 'charts-c3', 'charts-c4', 'charts-c5', 'd5', 'settings-account', 'imports-d6', 'brokers-security-d7'].includes(selectedCase)) {
  throw new Error(`Unknown browser case: ${selectedCase || '(missing)'}`)
}

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const browserDir = resolve(frontendRoot, 'tests/browser')
const artifactsDir = resolve(browserDir, 'artifacts')
const builtAppDir = resolve(artifactsDir, 'app')
const screenshotsDir = resolve(artifactsDir, 'screenshots')
const browserLog = resolve(artifactsDir, 'browser.log')
const authInit = resolve(browserDir, 'auth-init.js')

async function log(entry) {
  await appendFile(browserLog, `${JSON.stringify(entry)}\n`, 'utf8')
}

function routeSlug(routePath) {
  return routePath === '/' ? 'root' : routePath.slice(1).replaceAll('/', '-')
}

async function runRoute({ appOrigin, authenticated, route, session, viewport }) {
  const context = `${viewport.name} ${route.path}`
  const initScript = authenticated ? authInit : undefined
  await runAgentBrowser({ args: ['console', '--clear'], context: `${context} clear console`, initScript, log, session })
  await runAgentBrowser({
    args: ['errors', '--clear'],
    context: `${context} clear errors`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['open', `${appOrigin}${route.path}`],
    context: `${context} open`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['wait', '250'],
    context: `${context} settle`,
    initScript,
    log,
    session,
  })

  if (viewport.zoom !== 1) {
    await runAgentBrowser({
      args: ['eval', `document.documentElement.style.zoom = '${viewport.zoom}'`],
      context: `${context} apply CSS zoom`,
      initScript,
      log,
      session,
    })
  }

  const data = await runAgentBrowser({
    args: [
      'eval',
      `({ path: location.pathname, appChildren: document.querySelector('#app')?.childElementCount ?? 0, bodyTextLength: document.body.innerText.length, zoom: document.documentElement.style.zoom || '1' })`,
    ],
    context: `${context} probe`,
    initScript,
    log,
    session,
  })
  const expectedPath = route.expectedPath || route.path
  const probe = data.result

  if (
    probe.path !== expectedPath ||
    probe.appChildren < 1 ||
    probe.bodyTextLength < 1 ||
    String(probe.zoom) !== String(viewport.zoom)
  ) {
    throw new Error(`${context}: route probe failed: ${JSON.stringify({ expectedPath, probe })}`)
  }

  let geometry
  if (authenticated) {
    geometry = await assertLayoutGeometry({ context, initScript, log, session })
  }

  const errorData = await runAgentBrowser({
    args: ['errors'],
    context: `${context} page errors`,
    initScript,
    log,
    session,
  })
  if (errorData.errors.length > 0) {
    throw new Error(`${context}: page errors: ${JSON.stringify(errorData.errors)}`)
  }
  const consoleData = await runAgentBrowser({ args: ['console'], context: `${context} UI registration`, initScript, log, session })
  if (/Failed to resolve component|Failed to resolve directive|Unknown icon:/.test(JSON.stringify(consoleData))) {
    throw new Error(`${context}: unresolved UI registration: ${JSON.stringify(consoleData)}`)
  }

  await log({ authenticated, context, geometry, probe, status: 'passed' })
  console.log(`PASS ${context}`)
  return { context, geometry, probe }
}

async function main() {
  await mkdir(artifactsDir, { recursive: true })
  await rm(builtAppDir, { force: true, recursive: true })
  await rm(screenshotsDir, { force: true, recursive: true })
  await mkdir(screenshotsDir, { recursive: true })
  await writeFile(browserLog, '', 'utf8')

  const fixtureServer = await startFixtureServer({ longAccount: selectedCase === 'layout', contextFailures: selectedCase === 'context', dateFlow: selectedCase === 'dates', requestFlow: selectedCase === 'requests', recoveryFlow: selectedCase === 'recovery', d4Flow: selectedCase === 'd4', chartsC2Flow: selectedCase === 'charts-c2', chartsC3Flow: selectedCase === 'charts-c3' || selectedCase === 'charts-c5', chartsC4Flow: selectedCase === 'charts-c4' || selectedCase === 'charts-c5', settingsAccountFlow: selectedCase === 'settings-account', d5States: selectedCase === 'd5', importsD6Flow: selectedCase === 'imports-d6', brokersSecurityD7Flow: selectedCase === 'brokers-security-d7' })
  let appServer
  const sessions = new Map()
  const routeFailures = []
  const deliveryGraphs = {}
  let chartsC4PilotRan = false
  let chartsC5Ran = false

  await runBrowserHarnessLifecycle({
    run: async () => {
    process.env.VITE_API_URL = fixtureServer.origin
    await log({ fixtureOrigin: fixtureServer.origin, status: 'building fixture-bound app' })
    // C5a: missing flags mean the default-on release candidate, so every
    // pre-existing case that exercises the incumbent/rollback behavior builds
    // its base artifact with an EXPLICIT all-false rollback configuration.
    // Flag-off assertions keep their strength; the unflagged candidate is
    // built separately by the charts-c5 case. The saved keys ARE the real
    // VITE_* names — restoring shorthand keys here would leak 'false' into
    // every later artifact build in the same run.
    const baseFlagState = {
      VITE_NAV_ECHARTS_ENABLED: process.env.VITE_NAV_ECHARTS_ENABLED,
      VITE_ALLOCATION_ECHARTS_ENABLED: process.env.VITE_ALLOCATION_ECHARTS_ENABLED,
      VITE_SECURITY_ECHARTS_ENABLED: process.env.VITE_SECURITY_ECHARTS_ENABLED,
    }
    process.env.VITE_NAV_ECHARTS_ENABLED = 'false'
    process.env.VITE_ALLOCATION_ECHARTS_ENABLED = 'false'
    process.env.VITE_SECURITY_ECHARTS_ENABLED = 'false'
    let buildFailed = false
    try {
      await build({
        mode: 'browser-test',
        root: frontendRoot,
        build: { emptyOutDir: true, outDir: builtAppDir },
      })
    } catch (error) {
      buildFailed = true
      throw error
    } finally {
      for (const [key, value] of Object.entries(baseFlagState)) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
      await log({ status: buildFailed ? 'fixture-bound build failed' : 'fixture-bound build explicit all-false rollback flags' })
    }
    appServer = await startBuiltAppServer(builtAppDir, selectedCase === 'dialog-recovery')

    for (const viewport of selectedCase === 'brokers-security-d7' ? viewports.filter((entry) => ['desktop', 'tablet', 'mobile'].includes(entry.name)) : ['dialogs', 'd4', 'd5', 'settings-account', 'imports-d6'].includes(selectedCase) ? viewports.filter(entry => ['desktop', 'mobile'].includes(entry.name)) : ['dates', 'requests', 'recovery', 'delivery', 'dialog-recovery', 'charts-c2', 'charts-c3', 'charts-c4', 'charts-c5'].includes(selectedCase) ? viewports.filter((entry) => entry.name === 'desktop') : viewports) {
      for (const authenticated of selectedCase && selectedCase !== 'delivery' ? [true] : [false, true]) {
        const selectedRoutes = routes.filter((route) =>
          selectedCase === 'dialog-recovery' ? route.path === '/transactions' : selectedCase === 'dialogs' ? dialogRoutes.includes(route.path) : selectedCase === 'delivery' ? ['/login', '/profile', '/dashboard'].includes(route.path) && route.authenticated === authenticated : selectedCase === 'd4' ? ['/open-positions', '/closed-positions', '/transactions'].includes(route.path) : ['charts-c2', 'charts-c3'].includes(selectedCase) ? route.path === '/dashboard' : selectedCase === 'charts-c4' || selectedCase === 'charts-c5' ? ['/dashboard', '/database/securities/1'].includes(route.path) : selectedCase === 'requests' ? ['/database/fx', '/transactions'].includes(route.path) : selectedCase === 'dates' ? route.path === '/open-positions' : ['context', 'recovery'].includes(selectedCase) ? route.path === '/dashboard' : selectedCase === 'd5' ? d5FamilyRoutes.includes(route.path) : selectedCase === 'settings-account' ? route.path === '/profile/settings' : selectedCase === 'imports-d6' ? route.path === '/transactions' : selectedCase === 'brokers-security-d7' ? ['/profile/settings', '/database/securities/1'].includes(route.path) : selectedCase === 'layout'
            ? ['/dashboard', '/summary', '/profile', '/database'].includes(route.path)
            : route.authenticated === authenticated,
        )
        const session = `r1-${authenticated ? 'auth' : 'public'}-${viewport.name}-${process.pid}`
        const initScript = authenticated ? authInit : undefined
        sessions.set(session, initScript)
        await runAgentBrowser({
          args: ['open', `${appServer.origin}${selectedRoutes[0].path}`],
          context: `${viewport.name} launch ${authenticated ? 'authenticated' : 'public'} session`,
          initScript,
          log,
          session,
        })
        await runAgentBrowser({
          args: ['set', 'viewport', String(viewport.width), String(viewport.height)],
          context: `${viewport.name} set viewport`,
          initScript,
          log,
          session,
        })

        for (const route of selectedRoutes) {
          try {
            await runRoute({
              appOrigin: appServer.origin,
              authenticated,
              route,
              session,
              viewport,
            })
            if (selectedCase === 'dialog-recovery') await assertDialogChunkRecovery({ context: `${viewport.name} dialog download recovery`, initScript, log, session })
            if (selectedCase === 'dialogs') {
              await assertDialogDeliveryFlow({ context: `${viewport.name} ${route.path} dialogs`, initScript, log, session, route })
            }
            if (selectedCase === 'delivery') {
              await runAgentBrowser({ args: ['wait', '--load', 'networkidle'], context: `Settle cold resource graph ${route.path}`, initScript, log, session })
              const observed = await runAgentBrowser({
                args: ['eval', `performance.getEntriesByType('resource').map(entry => entry.name).filter(name => new URL(name).origin === location.origin)`],
                context: `Cold resource graph ${route.path}`, initScript, log, session,
              })
              const graph = await measureRouteBundles({ root: builtAppDir, resources: observed.result })
              deliveryGraphs[route.path] = graph
              await writeFile(resolve(artifactsDir, 'delivery.json'), JSON.stringify(deliveryGraphs, null, 2))
              assertRouteDelivery(route.path, graph)
            }
            if (selectedCase === 'recovery') {
              await assertDashboardRecoveryFlow({ context: `${viewport.name} dashboard recovery`, initScript, log, session, fixtureServer })
              console.log(`PASS ${viewport.name} dashboard recovery`)
            }
            if (selectedCase === 'requests') {
              await assertRequestOrderFlow({ context: `${viewport.name} ${route.path} request order`, initScript, log, session, fixtureServer, route })
              console.log(`PASS ${viewport.name} ${route.path} request order`)
            }
            if (selectedCase === 'd4') {
              if (viewport.name === 'desktop' && route.path === '/open-positions') {
                await assertD4TablesFlow({ appOrigin: appServer.origin, context: `${viewport.name} d4 tables`, initScript, log, session, fixtureServer })
              }
              if (viewport.name === 'desktop' && route.path === '/transactions') {
                await assertD4TransactionsFlow({ appOrigin: appServer.origin, context: `${viewport.name} d4 transactions`, initScript, log, session, fixtureServer })
              }
              await assertD4ViewportChecks({ appOrigin: appServer.origin, context: `${viewport.name} ${route.path} d4 viewport`, initScript, log, session, viewport, route: route.path })
            }
            if (selectedCase === 'd5') {
              await assertD5FamilyProbesFlow({ appOrigin: appServer.origin, context: `${viewport.name} ${route.path} d5 family`, initScript, log, session, route: route.path, fixtureServer })
            }
            if (selectedCase === 'charts-c2') {
              await assertChartsC2Flow({ appOrigin: appServer.origin, context: `${viewport.name} charts c2`, initScript, log, session, fixtureServer })
              console.log(`PASS ${viewport.name} charts c2 flow`)
            }
            if (selectedCase === 'settings-account') {
              await assertSettingsAccountFlow({ appOrigin: appServer.origin, context: `${viewport.name} settings account`, initScript, log, session, fixtureServer, viewport })
            }
            if (selectedCase === 'imports-d6') {
              await assertImportsD6Flow({ appOrigin: appServer.origin, context: `${viewport.name} imports d6`, initScript, log, session, fixtureServer, viewport })
            }
            if (selectedCase === 'brokers-security-d7') {
              await assertBrokersSecurityD7Flow({ appOrigin: appServer.origin, context: `${viewport.name} brokers-security-d7`, initScript, log, session, fixtureServer, viewport })
            }
            if (selectedCase === 'charts-c4') {
              await assertChartsC4FlagOffFlow({ appOrigin: appServer.origin, context: `${viewport.name} charts c4 flag-off`, initScript, log, session })
            }
            if (selectedCase === 'charts-c5' && !chartsC5Ran) {
              chartsC5Ran = true
              await runChartsC5Flow({
                appOrigin: appServer.origin,
                flagOffRoot: builtAppDir,
                frontendRoot,
                fixtureServer,
                log,
                registerSession: (extra) => sessions.set(extra, resolve(browserDir, 'auth-init.js')),
                artifactsDir,
              })
              console.log('PASS charts c5 flow')
            }
            if (selectedCase === 'charts-c3') {
              await assertChartsC3FlagOffFlow({ appOrigin: appServer.origin, context: `${viewport.name} charts c3 flag-off`, initScript, log, session })
              // The flag-on pilot phase builds its own artifact; its extra
              // session is registered up front for guaranteed cleanup.
              await runChartsC3PilotFlow({
                appOrigin: appServer.origin,
                flagOffRoot: builtAppDir,
                frontendRoot,
                fixtureServer,
                log,
                registerSession: (extra, extraInit) => sessions.set(extra, extraInit ?? resolve(browserDir, 'auth-init.js')),
                artifactsDir,
              })
              console.log(`PASS ${viewport.name} charts c3 pilot flow`)
            }
            if (selectedCase === 'charts-c4' && !chartsC4PilotRan) {
              chartsC4PilotRan = true
              await runChartsC4PilotFlow({
                appOrigin: appServer.origin,
                flagOffRoot: builtAppDir,
                frontendRoot,
                fixtureServer,
                log,
                registerSession: (extra) => sessions.set(extra, resolve(browserDir, 'auth-init.js')),
                artifactsDir,
              })
              console.log(`PASS charts c4 pilot flow`)
            }
          } catch (error) {
            if (selectedCase === 'charts-c4') console.error('C4-STACK', error.stack?.slice(0, 1400))
            routeFailures.push({ route: route.path, viewport: viewport.name, error: error.message })
            console.error(`FAIL ${viewport.name} ${route.path}: ${error.message}`)
            const screenshotPath = resolve(
              screenshotsDir,
              `${viewport.name}-${routeSlug(route.path)}.png`,
            )
            try {
              await runAgentBrowser({
                args: ['screenshot', screenshotPath],
                context: `${viewport.name} ${route.path} failure screenshot`,
                initScript,
                log,
                session,
              })
            } catch (screenshotError) {
              await log({ context: `${viewport.name} ${route.path}`, screenshotError: screenshotError.message })
            }
          }
        }
        if (selectedCase === 'context') {
          try {
            await assertContextFailureFlow({ context: `${viewport.name} context failure`, initScript, log, session, fixtureServer })
            console.log(`PASS ${viewport.name} context failure`)
          } catch (error) {
            fixtureServer.releaseMutation()
            routeFailures.push({ route: 'context failure', viewport: viewport.name, error: error.message })
            console.error(`FAIL ${viewport.name} context failure: ${error.message}`)
          }
        }
        if (selectedCase === 'dates') {
          try {
            const flow = await assertMountedDateFlow({ context: `${viewport.name} mounted date flow`, initScript, log, session, fixtureServer })
            await log({ context: `${viewport.name} mounted date flow`, flow, status: 'passed' })
            console.log(`PASS ${viewport.name} mounted date flow`)
          } catch (error) {
            routeFailures.push({ route: 'mounted date flow', viewport: viewport.name, error: error.message })
            console.error(`FAIL ${viewport.name} mounted date flow: ${error.message}`)
          }
        }
        if (selectedCase === 'layout') {
          try {
            const flow = await assertFocusedLayoutFlow({
              context: `${viewport.name} layout flow`,
              initScript,
              log,
              session,
              viewport,
            })
            await log({ context: `${viewport.name} layout flow`, flow, status: 'passed' })
            console.log(`PASS ${viewport.name} layout flow`)
          } catch (error) {
            routeFailures.push({ route: 'layout flow', viewport: viewport.name, error: error.message })
            console.error(`FAIL ${viewport.name} layout flow: ${error.message}`)
          }
          try {
            await assertPositionsToolbarFlow({
              appOrigin: appServer.origin,
              context: `${viewport.name} positions toolbar`,
              initScript,
              log,
              session,
              viewport,
            })
          } catch (error) {
            routeFailures.push({ route: 'positions toolbar', viewport: viewport.name, error: error.message })
            console.error(`FAIL ${viewport.name} positions toolbar: ${error.message}`)
          }
        }
      }
    }

    if (selectedCase === 'd5') {
      // Rendered-state acceptance (empty/error/filtered-empty with genuine
      // server-side filtering), then native 200% zoom on a dense data route,
      // then the family captures on a registered session for guaranteed
      // cleanup.
      const d5ShotsSession = `d5-shots-${process.pid}`
      sessions.set(d5ShotsSession, authInit)
      try {
        await assertD5StatesFlow({ appOrigin: appServer.origin, context: 'd5 states', initScript: authInit, log, session: d5ShotsSession, fixtureServer, registerSession: (extra) => sessions.set(extra, undefined) })
        await assertMobilePageControlsFlow({ appOrigin: appServer.origin, context: 'd5 mobile controls', initScript: authInit, log, session: d5ShotsSession })
        await assertD5NativeZoomFlow({ appOrigin: appServer.origin, context: 'd5 native zoom', initScript: authInit, log, session: d5ShotsSession })
        await captureD5Screenshots({ appOrigin: appServer.origin, context: 'd5 screenshots', initScript: authInit, log, session: d5ShotsSession, registerSession: (extra) => sessions.set(extra, undefined) })
      } catch (error) {
        routeFailures.push({ route: 'd5 zoom/captures', viewport: 'desktop', error: error.message })
        console.error(`FAIL d5 zoom/captures: ${error.message}`)
      }
    }
    if (selectedCase === 'd4') {
      // Register the screenshot session with the harness so the guaranteed
      // cleanup closes it even when the capture throws mid-way.
      const d4ShotsSession = `d4-shots-${process.pid}`
      sessions.set(d4ShotsSession, authInit)
      try {
        await captureD4Screenshots({ appOrigin: appServer.origin, context: 'd4 screenshots', initScript: authInit, log, session: d4ShotsSession })
      } catch (error) {
        routeFailures.push({ route: 'd4 screenshots', viewport: 'desktop', error: error.message })
        console.error(`FAIL d4 screenshots: ${error.message}`)
      }
    }

    const summary = {
      cssZoomMechanism: 'document.documentElement.style.zoom',
      fixtureMismatches: fixtureServer.unmatchedRequests,
      fixtureRequests: fixtureServer.requests.length,
      routeFailures,
      routeManifestCount: routes.length,
      routes: selectedCase === 'dialog-recovery' ? 1 : selectedCase === 'd4' ? 3 : selectedCase === 'dialogs' ? dialogRoutes.length : selectedCase === 'delivery' ? 3 : selectedCase === 'requests' ? 2 : ['dates', 'context', 'recovery', 'charts-c2', 'charts-c3', 'charts-c4', 'charts-c5'].includes(selectedCase) ? 1 : selectedCase === 'd5' ? d5FamilyRoutes.length : ['settings-account', 'imports-d6', 'brokers-security-d7'].includes(selectedCase) ? 2 : selectedCase === 'layout' ? 4 : routes.length,
      viewports: selectedCase === 'brokers-security-d7' ? 3 : ['d4', 'dialogs', 'd5', 'settings-account', 'imports-d6'].includes(selectedCase) ? 2 : ['dates', 'requests', 'recovery', 'delivery', 'dialog-recovery', 'charts-c2', 'charts-c3', 'charts-c4', 'charts-c5'].includes(selectedCase) ? 1 : viewports.length,
    }
    await writeFile(resolve(artifactsDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
    console.log(JSON.stringify(summary, null, 2))

    if (fixtureServer.unmatchedRequests.length > 0 || routeFailures.length > 0) {
      process.exitCode = 1
    }
    },
    cleanup: () =>
      cleanupBrowserHarness({
        sessions,
        closeSession: (session, initScript) =>
          runAgentBrowser({
            args: ['close'],
            context: `${session} close`,
            initScript,
            log,
            session,
          }),
        closeAppServer: appServer ? () => appServer.close() : undefined,
        closeFixtureServer: () => fixtureServer.close(),
        recordError: log,
      }),
  })
}

await main()
