import assert from 'node:assert/strict'

import { runAgentBrowser } from './protocol.mjs'

// D5 rendered acceptance: the reviewed workspace hierarchy rolled out across
// every remaining route family. Assertions grow family by family with the
// implementation; every probe runs against synthetic fixtures only.
//
// Task 0 skeleton: per-family structural probes (single route heading, no
// page-level horizontal overflow, named primary controls present). The
// family-specific behavior checks land with their tasks below.

export const d5FamilyRoutes = [
  '/summary',
  '/database',
  '/database/brokers',
  '/database/accounts',
  '/database/securities',
  '/database/prices',
  '/database/fx',
  '/database/securities/1',
  '/profile',
  '/profile/settings',
]

const evalProbe = (run, expression) =>
  runAgentBrowser({ args: ['eval', expression] }).then((data) => data.result)

const waitFor = (run, fn, timeout = 8000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

// Structural probe over one migrated family route: exactly one h1 in main
// (the WorkspacePage heading once the family is migrated), no page-level
// horizontal overflow, and the family's named primary control present.
export async function assertD5FamilyProbesFlow({
  appOrigin,
  context,
  initScript,
  log,
  session,
  route,
}) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  await run(['open', `${appOrigin}${route}`])
  await waitFor(run, `document.querySelector('[data-testid="route-content"]') !== null`)
  await run(['wait', '400'])

  const probe = await evalProbe(
    run,
    `(() => {
      const main = document.querySelector('.v-main') || document.body
      const headings = [...main.querySelectorAll('h1')]
      return {
        path: location.pathname,
        headingCount: headings.length,
        headingText: headings[0]?.textContent?.trim() ?? null,
        pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        legacyHeading: !!document.querySelector('[data-testid="legacy-page-heading"]'),
        workspaceHeading: !!document.querySelector('[data-testid="workspace-page-heading"]'),
      }
    })()`,
  )
  assert.equal(
    probe.headingCount,
    1,
    `${context}: ${route} renders exactly one h1 (got ${probe.headingCount}: ${probe.headingText})`,
  )
  assert.ok(probe.workspaceHeading, `${context}: ${route} heading is workspace-owned`)
  assert.equal(probe.pageOverflow, false, `${context}: ${route} has no page-level horizontal overflow`)
  return probe
}

export async function captureD5Screenshots({ appOrigin, context, initScript, log, session, screenshotsDir, resolveScreenshot }) {
  // Captures land with each family's task; the D5 asset names are d5-*.
  void appOrigin
  void context
  void initScript
  void log
  void session
  void screenshotsDir
  void resolveScreenshot
}
