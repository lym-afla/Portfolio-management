// Regenerate eslint-baseline.json from a live eslint run.
// Refuses to write when any severity-2 error exists (fix errors first);
// warnings are re-pinned at their current file/line/rule/message.
import { execFileSync } from 'node:child_process'
import { writeFileSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const baselinePath = resolve(frontend, 'eslint-baseline.json')

const raw = execFileSync(
  process.execPath,
  [
    resolve(frontend, 'node_modules', 'eslint', 'bin', 'eslint.js'),
    '--format', 'json',
    'src',
  ],
  { cwd: frontend, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, shell: true },
)
const results = JSON.parse(raw)
const diagnostics = []
let errors = 0
for (const file of results) {
  for (const message of file.messages) {
    if (message.severity === 2) {
      errors += 1
      console.error(`ERROR ${file.filePath}:${message.line} ${message.ruleId} ${message.message}`)
      continue
    }
    diagnostics.push({
      file: file.filePath.replace(resolve(frontend) + '\\', '').replaceAll('\\', '/'),
      line: message.line,
      column: message.column,
      ruleId: message.ruleId,
      message: message.message,
      severity: message.severity,
    })
  }
}
if (errors > 0) {
  console.error(`Refusing to regenerate baseline: ${errors} severity-2 error(s) present.`)
  process.exit(1)
}
const previous = JSON.parse(readFileSync(baselinePath, 'utf8'))
writeFileSync(baselinePath, JSON.stringify(diagnostics, null, 2) + '\n')
console.log(`Baseline regenerated: ${previous.length} -> ${diagnostics.length} entries.`)
