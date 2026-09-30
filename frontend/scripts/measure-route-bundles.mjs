import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve, sep } from 'node:path'
import { gzipSync } from 'node:zlib'

// Use observed cold requests, not only the entry chunk or manifest imports.
export async function measureRouteBundles({ root, resources }) {
  const manifest = JSON.parse(await readFile(resolve(root, '.vite/manifest.json'), 'utf8'))
  const membership = JSON.parse(await readFile(resolve(root, '.vite/module-membership.json'), 'utf8'))
  const assets = [...new Set(resources.map((url) => new URL(url).pathname.slice(1)))].sort()
  const files = []
  for (const asset of assets) {
    const target = resolve(root, asset)
    assert.ok(target.startsWith(`${resolve(root)}${sep}`), 'Asset must stay inside build output')
    if (!/\.(js|css)$/.test(asset)) continue
    const bytes = await readFile(target)
    files.push({ asset, bytes: bytes.length, gzipBytes: gzipSync(bytes).length })
  }
  const modules = assets.flatMap((asset) => membership[asset] || [])
  return {
    assets, files, modules,
    manifestEntries: Object.keys(manifest).length,
    gzipJsCss: files.reduce((total, file) => total + file.gzipBytes, 0),
  }
}

export function assertRouteDelivery(route, graph) {
  assert.ok(graph.gzipJsCss > 0, `${route}: complete graph must be measured`)
  assert.equal(graph.assets.some((path) => /materialdesignicons.*\.(woff2?|ttf|eot)/.test(path)), false, `${route}: full icon font downloaded`)
  assert.equal(graph.modules.some((path) => /\/utils\/(authDebugConsole|authDebug|axiosDebug)\./.test(path)), false, `${route}: production debug modules loaded`)
  assert.equal(graph.modules.some(path => /\/components\/dialogs\//.test(path)), false, `${route}: unopened dialog modules downloaded`)
  if (['/login', '/profile'].includes(route)) {
    assert.equal(graph.modules.some((path) => /\/components\/dashboard\/|\/views\/DashboardPage\.vue|\/node_modules\/(chart\.js|vue-chartjs)\//.test(path)), false, `${route}: dashboard or chart modules downloaded`)
  }
  if (route === '/dashboard') assert.ok(graph.gzipJsCss <= 401_000, `Dashboard ${graph.gzipJsCss} gzip bytes exceeds delivery target401000`)
}
