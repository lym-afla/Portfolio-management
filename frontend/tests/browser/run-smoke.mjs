import { readFile, rm, mkdir, writeFile, appendFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import { build } from 'vite'

import { startFixtureServer } from './fixture-server.mjs'
import { runAgentBrowser } from './protocol.mjs'
import { routes, viewports } from './routes.mjs'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const browserDir = resolve(frontendRoot, 'tests/browser')
const artifactsDir = resolve(browserDir, 'artifacts')
const builtAppDir = resolve(artifactsDir, 'app')
const screenshotsDir = resolve(artifactsDir, 'screenshots')
const browserLog = resolve(artifactsDir, 'browser.log')
const authInit = resolve(browserDir, 'auth-init.js')

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

function listen(server) {
  return new Promise((resolvePromise, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolvePromise())
  })
}

function close(server) {
  return new Promise((resolvePromise, reject) => {
    server.close((error) => (error ? reject(error) : resolvePromise()))
  })
}

async function startBuiltAppServer(root) {
  const indexPath = resolve(root, 'index.html')
  const server = createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname)
      const requestedPath = resolve(root, `.${pathname}`)
      const safePath = requestedPath === root || requestedPath.startsWith(`${root}${sep}`)
      if (!safePath) {
        response.writeHead(400)
        response.end('Invalid path')
        return
      }

      let filePath = requestedPath
      if (pathname === '/' || !extname(pathname)) {
        filePath = indexPath
      }
      const body = await readFile(filePath)
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': contentTypes[extname(filePath)] || 'application/octet-stream',
      })
      response.end(body)
    } catch {
      response.writeHead(404)
      response.end('Not found')
    }
  })

  await listen(server)
  const address = server.address()
  return { origin: `http://127.0.0.1:${address.port}`, close: () => close(server) }
}

async function log(entry) {
  await appendFile(browserLog, `${JSON.stringify(entry)}\n`, 'utf8')
}

function routeSlug(routePath) {
  return routePath === '/' ? 'root' : routePath.slice(1).replaceAll('/', '-')
}

async function runRoute({ appOrigin, authenticated, route, session, viewport }) {
  const context = `${viewport.name} ${route.path}`
  const initScript = authenticated ? authInit : undefined
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

  await log({ authenticated, context, probe, status: 'passed' })
  console.log(`PASS ${context}`)
  return { context, probe }
}

async function main() {
  await mkdir(artifactsDir, { recursive: true })
  await rm(builtAppDir, { force: true, recursive: true })
  await rm(screenshotsDir, { force: true, recursive: true })
  await mkdir(screenshotsDir, { recursive: true })
  await writeFile(browserLog, '', 'utf8')

  const fixtureServer = await startFixtureServer()
  let appServer
  const sessions = new Map()
  const routeFailures = []

  try {
    process.env.VITE_API_URL = fixtureServer.origin
    await log({ fixtureOrigin: fixtureServer.origin, status: 'building fixture-bound app' })
    await build({
      mode: 'browser-test',
      root: frontendRoot,
      build: { emptyOutDir: true, outDir: builtAppDir },
    })
    appServer = await startBuiltAppServer(builtAppDir)

    for (const viewport of viewports) {
      for (const authenticated of [false, true]) {
        const selectedRoutes = routes.filter((route) => route.authenticated === authenticated)
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
          } catch (error) {
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
      }
    }

    const summary = {
      cssZoomMechanism: 'document.documentElement.style.zoom',
      fixtureMismatches: fixtureServer.unmatchedRequests,
      fixtureRequests: fixtureServer.requests.length,
      routeFailures,
      routes: routes.length,
      viewports: viewports.length,
    }
    await writeFile(resolve(artifactsDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
    console.log(JSON.stringify(summary, null, 2))

    if (fixtureServer.unmatchedRequests.length > 0 || routeFailures.length > 0) {
      process.exitCode = 1
    }
  } finally {
    for (const [session, initScript] of sessions) {
      try {
        await runAgentBrowser({
          args: ['close'],
          context: `${session} close`,
          initScript,
          log,
          session,
        })
      } catch (error) {
        await log({ context: `${session} close`, error: error.message })
      }
    }
    await appServer?.close()
    await fixtureServer.close()
  }
}

await main()
