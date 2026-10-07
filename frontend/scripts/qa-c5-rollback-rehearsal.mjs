// C5a task 4 rollback rehearsal (local evidence, not committed): rebuild the
// app with each family flag false individually, then all three false, and
// record each artifact's identity (file list + combined SHA-256) locally.
import { createHash } from 'node:crypto'
import { readdir, readFile, writeFile, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { build } from 'vite'

const frontendRoot = resolve(process.argv[2] ?? '.')
const outRoot = resolve(frontendRoot, 'tests/browser/artifacts')

const configs = {
  'nav-off': { VITE_NAV_ECHARTS_ENABLED: 'false', VITE_ALLOCATION_ECHARTS_ENABLED: 'true', VITE_SECURITY_ECHARTS_ENABLED: 'true' },
  'allocation-off': { VITE_NAV_ECHARTS_ENABLED: 'true', VITE_ALLOCATION_ECHARTS_ENABLED: 'false', VITE_SECURITY_ECHARTS_ENABLED: 'true' },
  'security-off': { VITE_NAV_ECHARTS_ENABLED: 'true', VITE_ALLOCATION_ECHARTS_ENABLED: 'true', VITE_SECURITY_ECHARTS_ENABLED: 'false' },
  'all-off': { VITE_NAV_ECHARTS_ENABLED: 'false', VITE_ALLOCATION_ECHARTS_ENABLED: 'false', VITE_SECURITY_ECHARTS_ENABLED: 'false' },
}

const report = { rebuiltAt: new Date().toISOString(), node: process.version, artifacts: {} }
for (const [name, flags] of Object.entries(configs)) {
  const dir = resolve(outRoot, `rehearsal-${name}`)
  await rm(dir, { force: true, recursive: true })
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
  const entries = await readdir(dir, { recursive: true, withFileTypes: true })
  const files = entries.filter((entry) => entry.isFile())
    .map((entry) => (entry.parentPath ? `${entry.parentPath}/${entry.name}` : entry.name))
    .map((file) => file.split('\\').join('/'))
    .sort()
  const hasher = createHash('sha256')
  const manifest = []
  for (const file of files) {
    const bytes = await readFile(resolve(dir, file))
    const fileHash = createHash('sha256').update(bytes).digest('hex')
    hasher.update(`${file}:${fileHash}\n`)
    manifest.push({ file, bytes: bytes.length, sha256: fileHash })
  }
  report.artifacts[name] = {
    flags,
    dir: `tests/browser/artifacts/rehearsal-${name}`,
    files: manifest.length,
    combinedSha256: hasher.digest('hex'),
    entry: manifest.find((m) => /^index-.*\.js$/.test(m.file.split(/[\\/]/).pop())) ?? null,
  }
  console.log(`${name}: ${manifest.length} files, combined sha256 ${report.artifacts[name].combinedSha256.slice(0, 16)}…`)
}
await writeFile(resolve(outRoot, 'charts-c5-rollback-rehearsal.json'), `${JSON.stringify(report, null, 2)}\n`)
console.log('rollback rehearsal recorded in tests/browser/artifacts/charts-c5-rollback-rehearsal.json')
