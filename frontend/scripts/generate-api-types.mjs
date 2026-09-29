import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backend = resolve(frontend, '..', 'backend')
const output = resolve(frontend, 'src', 'types', 'api.d.ts')
const mode = process.argv[2]
if (mode !== '--check' && mode !== '--write') {
  throw new Error('Use --check or --write')
}
function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }, maxBuffer: 32 * 1024 * 1024 })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${command} failed: ${result.stderr || result.stdout}`)
  return result.stdout
}
const temporary = await mkdtemp(join(tmpdir(), 'portfolio-openapi-'))
try {
  const schema = join(temporary, 'schema.json')
  const generated = join(temporary, 'api.d.ts')
  await writeFile(schema, run('uv', ['run', 'python', 'manage.py', 'spectacular', '--format', 'openapi-json'], backend))
  run(process.execPath, [resolve(frontend, 'node_modules', 'openapi-typescript', 'bin', 'cli.js'), schema, '-o', generated], frontend)
  const actual = await readFile(generated, 'utf8')
  if (mode === '--check') {
    const current = await readFile(output, 'utf8')
    if (actual.replaceAll('\r\n', '\n') !== current.replaceAll('\r\n', '\n')) {
      console.error('Generated API types differ from src/types/api.d.ts. Run npm run api:types:generate and review the diff.')
      process.exitCode = 1
    } else {
      console.log('Generated API types match src/types/api.d.ts.')
    }
  } else {
    await writeFile(output, actual)
    console.log('Generated API types written to src/types/api.d.ts.')
  }
} finally {
  await rm(temporary, { recursive: true, force: true })
}
