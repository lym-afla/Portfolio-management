import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const eslintCli = resolve(dirname(fileURLToPath(import.meta.resolve('eslint'))), '../bin/eslint.js')

const probes = [
  {
    filename: 'src/__lint_probe__.ts',
    source: 'const answer: number = missingTypeScriptIdentifier\nvoid answer\n',
  },
  {
    filename: 'src/__lint_probe__.vue',
    source:
      '<template><div>probe</div></template>\n' +
      '<script setup lang="ts">\nmissingVueIdentifier()\n</script>\n',
  },
]

for (const probe of probes) {
  const result = spawnSync(
    process.execPath,
    [eslintCli, '--stdin', '--stdin-filename', probe.filename, '--format', 'json'],
    {
      cwd: new URL('..', import.meta.url),
      encoding: 'utf8',
      input: probe.source,
    },
  )

  if (result.error) {
    throw result.error
  }

  let report
  try {
    report = JSON.parse(result.stdout)
  } catch {
    throw new Error(
      `ESLint did not return JSON for ${probe.filename}: ${result.stderr || result.stdout}`,
    )
  }

  const messages = report.flatMap((entry) => entry.messages)
  if (result.status === 0 || !messages.some((message) => message.ruleId === 'no-undef')) {
    throw new Error(
      `Lint scope probe for ${probe.filename} did not report its undefined identifier. ` +
        `Received: ${JSON.stringify(messages)}`,
    )
  }
}

console.log('Lint scope probes detected undefined identifiers in TypeScript and Vue inputs.')
