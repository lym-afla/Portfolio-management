import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'
import { assertLayoutGeometry } from './layout.mjs'

const here = dirname(fileURLToPath(import.meta.url))

export function routeSlug(routePath) {
  return routePath === '/' ? 'root' : routePath.slice(1).replaceAll('/', '-')
}

// The shared per-route probe: clear console/errors, open, settle, apply the
// viewport's CSS zoom (the zoom-200 viewport is CSS-level; native zoom is a
// separate CDP flow), probe the rendered route, then check geometry, page
// errors and UI registration. Used by the rollback matrix in run-smoke.mjs
// and by the D8 default-on matrix, so both matrices assert identically.
export async function runRoute({ appOrigin, authenticated, route, session, viewport, log }) {
  const context = `${viewport.name} ${route.path}`
  const initScript = authenticated ? resolve(here, 'auth-init.js') : undefined
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
