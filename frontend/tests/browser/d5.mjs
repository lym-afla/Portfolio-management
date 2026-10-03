import assert from 'node:assert/strict'

import { runAgentBrowser } from './protocol.mjs'

// D5 rendered acceptance: the reviewed workspace hierarchy rolled out across
// every remaining route family. Assertions grow family by family with the
// implementation; every probe runs against synthetic fixtures only.

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

const openSelectByTestId = async (run, testid) => {
  await run(['eval', `(() => { const root = document.querySelector('[data-testid="${testid}"]'); const field = root?.querySelector('.v-field'); field?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); field?.dispatchEvent(new MouseEvent('click', { bubbles: true })); return !!field })()`])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active .v-list-item').length > 0`)
}

const pickOverlayItem = async (run, label) => {
  await run(['eval', `(() => { const item = [...document.querySelectorAll('.v-overlay--active .v-list-item')].find(el => el.textContent.trim().startsWith('${label}')); if (!item) throw new Error('overlay item ${label} missing'); item.click(); return true })()`])
  await run(['wait', '150'])
  await run(['wait', '--fn', `document.querySelector('.v-overlay--active .v-list-item') === null`])
}

// /summary family: period control, all eight leaves in every mode, groups/
// sub-totals/TOTAL, exact strings, presentation-only view switches and the
// breakdown-year filter's independent request ownership.
async function assertD5SummaryFlow({ appOrigin, context, initScript, log, session, fixtureServer }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const summaryRequests = () => fixtureServer.requests.filter((entry) => entry.path === '/summary/api/summary_data/').length

  await run(['open', `${appOrigin}/summary`])
  // The performance query legitimately re-runs once when the initial
  // context reconciliation bumps the revision; wait for the SETTLED table
  // (skeleton gone) instead of the first appearance.
  await waitFor(run, `!!document.querySelector('.account-performance-table') && !document.querySelector('.v-skeleton-loader')`)
  await run(['wait', '300'])
  await waitFor(run, `!!document.querySelector('.account-performance-table') && !document.querySelector('.v-skeleton-loader')`)

  // Single-period default: YTD flat qualified leaves, exact strings, groups.
  let probe = await evalProbe(run, `(() => {
    const table = document.querySelector('.account-performance-table')
    if (!table) throw new Error('settled summary table missing')
    const headers = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim())
    return {
      headers,
      groups: [...table.querySelectorAll('tbody tr.group-header')].map((tr) => tr.textContent.trim()),
      totalRow: [...table.querySelectorAll('tbody tr.total-row')].map((tr) => tr.textContent.trim()),
      subtotalRows: table.querySelectorAll('tbody tr.subtotal-row').length,
      hasCommaValue: table.textContent.includes('$10,000.00'),
      hasNa: table.textContent.includes('N/A'),
    }
  })()`)
  assert.equal(probe.headers.length, 9, `${context}: summary single-period header cell count`)
  assert.equal(probe.headers[0], 'Account', `${context}: account identity column`)
  for (const label of ['BoP NAV (YTD)', 'Cash-in/(out) (YTD)', 'Return (YTD)', 'FX (YTD)', 'TSR (YTD)', 'EoP NAV (YTD)', 'Commissions (YTD)', 'Fee per AuM (YTD)']) {
    assert.ok(probe.headers.includes(label), `${context}: leaf ${label} present`)
  }
  assert.deepEqual(probe.groups, ['Public Markets', 'Restricted Investments'], `${context}: both groups`)
  assert.equal(probe.totalRow.length, 1, `${context}: one TOTAL row`)
  assert.ok(probe.totalRow[0].startsWith('TOTAL'), `${context}: TOTAL row identity`)
  assert.ok(probe.subtotalRows >= 2, `${context}: sub-total lines render per group`)
  assert.equal(probe.hasCommaValue, true, `${context}: comma-grouped server string verbatim`)
  assert.equal(probe.hasNa, true, `${context}: N/A markers render`)

  // View switches are presentation-only: no additional summary request.
  const before = summaryRequests()
  await openSelectByTestId(run, 'performance-period-select')
  await pickOverlayItem(run, '2024')
  probe = await evalProbe(run, `(() => ({
    headers: [...document.querySelectorAll('.account-performance-table thead th')].map((th) => th.textContent.trim()),
  }))()`)
  assert.ok(probe.headers.includes('BoP NAV (2024)'), `${context}: period switch re-qualifies leaf labels`)
  await openSelectByTestId(run, 'performance-view-select')
  await pickOverlayItem(run, 'Comparison')
  await run(['wait', '150'])
  await openSelectByTestId(run, 'performance-view-select')
  await pickOverlayItem(run, 'Full history')
  probe = await evalProbe(run, `(() => {
    const bands = [...document.querySelectorAll('.account-performance-table thead .period-band')].map((th) => th.textContent.trim())
    const headerRows = document.querySelectorAll('.account-performance-table thead tr').length
    return { bands, headerRows, leafCells: document.querySelectorAll('.account-performance-table thead th[scope="col"]').length }
  })()`)
  assert.equal(probe.headerRows, 2, `${context}: history uses grouped two-tier headers`)
  assert.deepEqual(probe.bands, ['YTD', '2025', '2024', 'All-time'], `${context}: every returned period in server order`)
  assert.equal(probe.leafCells, 4 * 8, `${context}: every leaf under every period`)
  const after = summaryRequests()
  assert.equal(after, before, `${context}: view/period switches made no additional summary request`)

  // Breakdown table: reactive units, populated values, year select present.
  probe = await evalProbe(run, `(() => {
    const table = document.querySelector('.portfolio-breakdown-table')
    return {
      text: table?.textContent ?? '',
      yearSelect: !!document.querySelector('[data-testid="breakdown-year-select"]'),
      region: !!document.querySelector('[data-testid="account-performance-region"]'),
    }
  })()`)
  assert.ok(probe.text.includes('(USD)'), `${context}: breakdown units labelled with reporting currency`)
  assert.ok(probe.text.includes('$80,000.00'), `${context}: breakdown value verbatim`)
  assert.equal(probe.yearSelect, true, `${context}: breakdown year control present`)
  assert.equal(probe.region, true, `${context}: performance table scrolls table-locally`)

  // The breakdown-year select still owns its request.
  const breakdownBefore = fixtureServer.requests.filter((entry) => entry.path === '/summary/api/portfolio_breakdown/').length
  await openSelectByTestId(run, 'breakdown-year-select')
  await pickOverlayItem(run, '2026')
  await run(['wait', '400'])
  const breakdownAfter = fixtureServer.requests.filter((entry) => entry.path === '/summary/api/portfolio_breakdown/').length
  assert.ok(breakdownAfter > breakdownBefore, `${context}: breakdown year change issues its own request`)
}

// Structural probe over one migrated family route: exactly one h1 in main
// (the WorkspacePage heading once the family is migrated), no page-level
// horizontal overflow.
export async function assertD5FamilyProbesFlow({
  appOrigin,
  context,
  initScript,
  log,
  session,
  route,
  fixtureServer,
}) {
  if (route === '/summary') {
    await assertD5SummaryFlow({ appOrigin, context, initScript, log, session, fixtureServer })
    console.log(`PASS ${context} summary flow`)
  }

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
