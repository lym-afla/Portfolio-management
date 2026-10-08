import { readdir, readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'

// Pure release-flag artifact helpers for the D8 final-QA case (and its unit
// regressions). Deliberately dependency-free: no vite, no browser harness.

// The real release-flag environment keys (the saved names ARE the wire names).
export const D8_FLAG_KEYS = [
  'VITE_NAV_ECHARTS_ENABLED',
  'VITE_ALLOCATION_ECHARTS_ENABLED',
  'VITE_SECURITY_ECHARTS_ENABLED',
]

// Apply a release-flag configuration for the duration of `fn` and restore the
// previous process.env afterwards — including through a build failure. A null
// flag value means the key must be genuinely ABSENT for the build (the
// default-on candidate), not merely inherited; a string value is set
// verbatim ('false' selects the rollback renderer policy).
export async function withFlagEnvironment(flags, fn) {
  const previous = {}
  for (const key of Object.keys(flags)) previous[key] = process.env[key]
  try {
    for (const [key, value] of Object.entries(flags)) {
      if (value === null) delete process.env[key]
      else process.env[key] = value
    }
    return await fn()
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
}

// Parse every .env* file in the frontend root and report which release-flag
// keys they define. A flag defined in ANY env file would leak into builds
// whose process.env keys were deleted (Vite loads env files by mode), so the
// default-on candidate is only genuine when this scan finds none.
export async function scanFlagEnvFiles(frontendRoot) {
  const entries = await readdir(frontendRoot)
  const files = []
  const flagKeysFound = []
  for (const entry of entries.filter((name) => name.startsWith('.env'))) {
    const file = resolve(frontendRoot, entry)
    const content = await readFile(file, 'utf8')
    const defined = {}
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const match = /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(trimmed)
      if (!match) continue
      const [, key, rawValue] = match
      const value = rawValue.replace(/^["']|["']$/g, '')
      defined[key] = value
      if (D8_FLAG_KEYS.includes(key)) flagKeysFound.push({ file: entry, key, value })
    }
    files.push({ file: entry, keys: Object.keys(defined), flags: defined })
  }
  return { files, flagKeysFound }
}

// Deterministic content hash of a built artifact: sha256 over the sorted
// relative file paths and their individual sha256 digests. Recorded in the
// evidence so reviewers can reproduce the exact audited bytes.
export async function hashArtifact(dir) {
  const walk = async (relative) => {
    const entries = await readdir(resolve(dir, relative), { withFileTypes: true })
    const found = []
    for (const entry of entries) {
      const child = relative ? `${relative}/${entry.name}` : entry.name
      if (entry.isDirectory()) found.push(...(await walk(child)))
      else found.push(child)
    }
    return found
  }
  const files = (await walk('')).sort()
  const digest = createHash('sha256')
  let totalBytes = 0
  for (const file of files) {
    const bytes = await readFile(resolve(dir, file))
    totalBytes += bytes.length
    digest.update(`${file}:${createHash('sha256').update(bytes).digest('hex')}\n`)
  }
  return { sha256: digest.digest('hex'), files: files.length, bytes: totalBytes }
}
