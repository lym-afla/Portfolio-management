import { execFile } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const cliPath = resolve(frontendRoot, 'node_modules/agent-browser/bin/agent-browser.js')

export function parseCliResult(stdout, context) {
  let envelope
  try {
    envelope = JSON.parse(stdout.trim())
  } catch {
    throw new Error(`${context}: agent-browser returned malformed JSON: ${stdout}`)
  }

  if (
    typeof envelope !== 'object' ||
    envelope === null ||
    typeof envelope.success !== 'boolean' ||
    !Object.hasOwn(envelope, 'data') ||
    !Object.hasOwn(envelope, 'error')
  ) {
    throw new Error(`${context}: agent-browser returned an unknown JSON envelope`)
  }

  if (!envelope.success) {
    throw new Error(`${context}: ${envelope.error || 'agent-browser command failed'}`)
  }

  return envelope.data
}

export async function runAgentBrowser({ args, context, initScript, log, session }) {
  const cliArgs = [
    cliPath,
    '--session',
    session,
    '--json',
    '--allowed-domains',
    '127.0.0.1',
    ...(initScript ? ['--init-script', initScript] : []),
    ...args,
  ]
  let result
  try {
    result = await execFileAsync(process.execPath, cliArgs, {
      cwd: frontendRoot,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      timeout: 30_000,
      windowsHide: true,
    })
  } catch (error) {
    await log?.({ args, context, stderr: error.stderr, stdout: error.stdout })
    if (error.stdout) {
      return parseCliResult(error.stdout, context)
    }
    throw error
  }

  await log?.({ args, context, stderr: result.stderr, stdout: result.stdout })
  return parseCliResult(result.stdout, context)
}
