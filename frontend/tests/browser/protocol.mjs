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
    // The execFile timeout kills the agent-browser.js node wrapper, but its
    // child CLI binary survives holding the stdio pipes, so the underlying
    // promise can never settle (observed: a wedged daemon stalled one command
    // indefinitely while every later command failed). Race a hard watchdog so
    // a wedged daemon becomes a fast, attributable failure instead.
    const exec = execFileAsync(process.execPath, cliArgs, {
      cwd: frontendRoot,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      timeout: 30_000,
      windowsHide: true,
    })
    let settled = false
    exec.catch(() => {})
    let watchdogTimer = null
    const watchdog = new Promise((resolveUnused, rejectWatchdog) => {
      watchdogTimer = setTimeout(() => {
        if (!settled) rejectWatchdog(new Error(`${context}: agent-browser command exceeded 45s (daemon wedge suspected)`))
      }, 45_000)
    })
    try {
      result = await Promise.race([exec.then((value) => { settled = true; return value }), watchdog])
      settled = true
    } finally {
      // A completed command must not leave its 45s timer holding the process
      // alive for up to 45 more seconds (thousands of commands per run).
      clearTimeout(watchdogTimer)
    }
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
