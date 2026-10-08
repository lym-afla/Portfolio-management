// Shared static server for built app artifacts in browser cases (extracted
// from run-smoke so focused cases can serve their own flag-specific builds).
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, resolve, sep } from 'node:path'

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
    // A page-held WebSocket or keep-alive socket would stall close() forever
    // (observed: an un-upgraded WS request left the raw socket open after the
    // D8 case's last page load). Drop every connection explicitly.
    try { server.closeAllConnections() } catch { /* Node without closeAllConnections */ }
    server.close((error) => (error ? reject(error) : resolvePromise()))
  })
}

export async function startBuiltAppServer(root, failDialogChunk = false) {
  const indexPath = resolve(root, 'index.html')
  const server = createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname)
      if (failDialogChunk && /^\/assets\/TransactionImportDialog-[^/]+\.js$/.test(pathname)) {
        failDialogChunk = false
        response.writeHead(503)
        response.end('Synthetic dialog download failure')
        return
      }
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
