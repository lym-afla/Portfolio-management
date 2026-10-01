import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

import { build } from 'vite'

import { startFixtureServer } from '../tests/browser/fixture-server.mjs'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const builtAppDir = resolve(frontendRoot, 'tests/browser/artifacts/qa-app')

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

const fixtureServer = await startFixtureServer({ longAccount: true })
process.env.VITE_API_URL = fixtureServer.origin
// Windows: rolldown-vite fails to resolve the index.html entry when root is a
// backslash absolute path; the cwd + relative outDir form matches run-smoke.
await build({
  mode: 'browser-test',
  root: process.cwd(),
  build: { emptyOutDir: true, outDir: 'tests/browser/artifacts/qa-app' },
})

const indexPath = resolve(builtAppDir, 'index.html')
const appServer = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname)
    const requestedPath = resolve(builtAppDir, `.${pathname}`)
    const safePath = requestedPath === builtAppDir || requestedPath.startsWith(`${builtAppDir}${sep}`)
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

await new Promise((resolveListen, reject) => {
  appServer.once('error', reject)
  appServer.listen(5189, '127.0.0.1', () => resolveListen())
})
console.log(`FIXTURE_ORIGIN=${fixtureServer.origin}`)
console.log('APP_ORIGIN=http://127.0.0.1:5189')
console.log('QA_READY')

const shutdown = async () => {
  appServer.close()
  await fixtureServer.close()
  process.exit(0)
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
await delay(24 * 60 * 60 * 1000)
