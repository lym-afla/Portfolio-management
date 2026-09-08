import { readFile } from 'node:fs/promises'
import { relative } from 'node:path'
import process from 'node:process'

import { ESLint } from 'eslint'

const eslint = new ESLint()
const results = await eslint.lintFiles([
  'src/**/*.{js,ts,vue}',
  'tests/**/*.{js,ts}',
  'scripts/**/*.mjs',
  'tests/browser/**/*.mjs',
])
const formatter = await eslint.loadFormatter('stylish')
const formatted = formatter.format(results)

if (formatted) {
  process.stdout.write(formatted)
}

const actual = results.flatMap((result) =>
  result.messages.map((message) => ({
    file: relative(process.cwd(), result.filePath).replaceAll('\\', '/'),
    line: message.line,
    column: message.column,
    ruleId: message.ruleId,
    message: message.message,
    severity: message.severity,
  })),
)

const baselineUrl = new URL('../eslint-baseline.json', import.meta.url)
const expected = JSON.parse(await readFile(baselineUrl, 'utf8'))
const fingerprint = (diagnostic) => JSON.stringify(diagnostic)
const expectedSet = new Set(expected.map(fingerprint))
const actualSet = new Set(actual.map(fingerprint))
const newDiagnostics = actual.filter((diagnostic) => !expectedSet.has(fingerprint(diagnostic)))
const staleDiagnostics = expected.filter((diagnostic) => !actualSet.has(fingerprint(diagnostic)))

if (newDiagnostics.length > 0 || staleDiagnostics.length > 0) {
  if (newDiagnostics.length > 0) {
    console.error(`New lint diagnostics (${newDiagnostics.length}):`)
    console.error(JSON.stringify(newDiagnostics, null, 2))
  }
  if (staleDiagnostics.length > 0) {
    console.error(`Stale lint baseline entries (${staleDiagnostics.length}):`)
    console.error(JSON.stringify(staleDiagnostics, null, 2))
  }
  process.exitCode = 1
}
