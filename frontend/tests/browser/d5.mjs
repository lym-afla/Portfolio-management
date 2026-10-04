import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'

// D5 rendered acceptance: the reviewed workspace hierarchy rolled out across
// every remaining route family. Assertions grow family by family with the
// implementation; every probe runs against synthetic fixtures only.

const here = dirname(fileURLToPath(import.meta.url))

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

const DESIGN_ASSETS = resolve(process.cwd(), '../docs/design/assets/frontend-workspace')

// Route every probe through the caller's `run` so it carries the SAME
// session/init-script as the flow (a bare runAgentBrowser call would land
// in the CLI's default context, i.e. a stale blank tab).
const evalProbe = (run, expression) =>
  run(['eval', expression]).then((data) => data.result)

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

const hitTest = (run, selector, label) =>
  evalProbe(run, `(() => {
    const el = document.querySelector('${selector}')
    if (!el) return { ok: false, reason: 'missing' }
    const rect = el.getBoundingClientRect()
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return { ok: el.contains(hit) || hit === el, hit: hit?.tagName ?? null }
  })()`).then((result) => {
    assert.ok(result.ok, `${label} control is elementFromPoint-hittable (hit ${result.hit})`)
    return result
  })

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
  // 32 leaf columns + the rowspan Account identity column, all scope=col.
  assert.equal(probe.leafCells, 4 * 8 + 1, `${context}: every leaf under every period`)
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

// Per-family behavior probes beyond the structural single-heading check.
const familyFlows = {
  '/database': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      heading: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent.trim(),
      landing: !!document.querySelector('h2#database-landing'),
      links: [...document.querySelectorAll('a')].map((a) => a.getAttribute('href')).filter((href) => href && href.startsWith('/database')),
    }))()`)
    assert.equal(probe.heading, 'Data', `${context}: Data heading`)
    assert.equal(probe.landing, true, `${context}: bare /database shows the landing section`)
    for (const child of ['/database/brokers', '/database/accounts', '/database/securities', '/database/prices', '/database/fx']) {
      assert.ok(probe.links.includes(child), `${context}: landing links to ${child}`)
    }
  },
  '/database/brokers': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      sectionHeading: document.querySelector('h2#brokers-section')?.textContent.trim(),
      addAction: !!document.querySelector('[data-testid="add-broker"]'),
      toolbarSearch: !!document.querySelector('.workspace-table-toolbar input'),
      rowActions: [...document.querySelectorAll('.v-data-table tbody .workspace-row-action')].map((b) => b.getAttribute('aria-label')),
      totalFooter: [...document.querySelectorAll('.v-data-table tfoot tr')].map((tr) => tr.textContent.trim()),
    }))()`)
    assert.equal(probe.sectionHeading, 'Brokers', `${context}: brokers section heading`)
    assert.equal(probe.addAction, true, `${context}: primary Add Broker`)
    assert.equal(probe.toolbarSearch, true, `${context}: shared toolbar search`)
    assert.ok(probe.rowActions.length >= 2, `${context}: named row actions`)
    assert.ok(probe.rowActions.every((label) => label && label.includes('Fixture Broker')), `${context}: row actions name their broker`)
    assert.ok(probe.totalFooter.length >= 1, `${context}: TOTAL footer row`)
  },
  '/database/accounts': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      sectionHeading: document.querySelector('h2#accounts-section')?.textContent.trim(),
      addAction: !!document.querySelector('[data-testid="add-account"]'),
      currencyColumns: [...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim()),
    }))()`)
    assert.equal(probe.sectionHeading, 'Accounts', `${context}: accounts section heading`)
    assert.equal(probe.addAction, true, `${context}: primary Add Account`)
    assert.ok(probe.currencyColumns.includes('USD'), `${context}: dynamic cash currency column`)
  },
  '/database/securities': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      sectionHeading: document.querySelector('h2#securities-section')?.textContent.trim(),
      detailLink: document.querySelector('h2#securities-section')?.closest('section')?.querySelector('a[href="/database/securities/1"]')?.textContent.trim() ?? null,
      merger: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Record Merger'),
      addSecurity: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Add Security'),
    }))()`)
    assert.equal(probe.sectionHeading, 'Securities', `${context}: securities section heading`)
    assert.equal(probe.detailLink, 'Fixture Security', `${context}: original detail link by id`)
    assert.equal(probe.merger, true, `${context}: Record Merger reachable`)
    assert.equal(probe.addSecurity, true, `${context}: Add Security primary`)
  },
  '/database/prices': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      sectionHeading: document.querySelector('h2#prices-section')?.textContent.trim(),
      filters: ['Asset Types', 'Accounts', 'Securities', 'Start Date', 'End Date'].map((label) => [...document.querySelectorAll('label')].some((l) => l.textContent.trim() === label)),
      apply: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Apply Filters'),
      addPrice: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Add Price Entry'),
      importPrices: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Import Prices'),
      priceCell: document.querySelector('h2#prices-section')?.closest('section')?.querySelector('.v-data-table')?.textContent.includes('100.00'),
    }))()`)
    assert.equal(probe.sectionHeading, 'Prices', `${context}: prices section heading`)
    assert.ok(probe.filters.every(Boolean), `${context}: security/date/source filter controls labelled`)
    assert.equal(probe.apply, true, `${context}: Apply Filters retained`)
    assert.equal(probe.addPrice, true, `${context}: Add Price Entry primary`)
    assert.equal(probe.importPrices, true, `${context}: Import Prices secondary`)
    assert.equal(probe.priceCell, true, `${context}: price string verbatim`)
  },
  '/database/fx': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      sectionHeading: document.querySelector('h2#fx-section')?.textContent.trim(),
      orientationNote: document.querySelector('h2#fx-section')?.closest('section')?.textContent.includes('quoted from the first currency to the second'),
      pairHeaders: [...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim()),
      filledCell: document.querySelector('h2#fx-section')?.closest('section')?.querySelector('.cell-btn--filled')?.textContent.trim() ?? null,
      emptyCell: document.querySelector('h2#fx-section')?.closest('section')?.querySelector('.cell-btn--empty')?.textContent.trim() ?? null,
      dateRange: !!document.querySelector('.workspace-table-toolbar__filters button'),
      addFx: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Add FX Rate'),
      importFx: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Import FX Rates'),
    }))()`)
    assert.equal(probe.sectionHeading, 'FX rates', `${context}: fx section heading`)
    assert.equal(probe.orientationNote, true, `${context}: from->to orientation note`)
    assert.ok(probe.pairHeaders.includes('USD/EUR'), `${context}: pair label`)
    assert.equal(probe.filledCell, '0.9500', `${context}: rate value verbatim`)
    assert.equal(probe.emptyCell, '—', `${context}: missing cell marker`)
    assert.equal(probe.dateRange, true, `${context}: date range selector`)
    assert.equal(probe.addFx, true, `${context}: Add FX Rate primary`)
    assert.equal(probe.importFx, true, `${context}: Import FX Rates secondary`)
  },
  '/database/securities/1': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      heading: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent.trim(),
      description: document.querySelector('.workspace-page__header .workspace-meta')?.textContent.trim() ?? null,
      basic: !!document.querySelector('h2#security-basic'),
      performance: !!document.querySelector('h2#security-performance'),
      accountScope: [...document.querySelectorAll('label')].some((l) => l.textContent.trim() === 'Broker Account'),
    }))()`)
    assert.equal(probe.heading, 'Fixture Security', `${context}: detail heading is the security name`)
    assert.ok(probe.description && probe.description.includes('Stock'), `${context}: identity description line`)
    assert.equal(probe.basic, true, `${context}: basic information section`)
    assert.equal(probe.performance, true, `${context}: performance metrics section`)
    assert.equal(probe.accountScope, true, `${context}: account scope selector`)
  },
  '/profile': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      heading: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent.trim(),
      navLinks: [...document.querySelectorAll('.profile-layout__nav a')].map((a) => a.getAttribute('href')),
      userDetails: document.querySelector('h2#user-details-section')?.textContent.trim(),
      logout: [...document.querySelectorAll('.profile-layout__nav button, .profile-layout__nav .v-list-item')].some((el) => el.textContent.trim() === 'Logout'),
      deleteAccount: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Delete Account'),
    }))()`)
    assert.equal(probe.heading, 'Profile', `${context}: profile heading`)
    assert.ok(probe.navLinks.includes('/profile'), `${context}: details nav`)
    assert.ok(probe.navLinks.includes('/profile/settings'), `${context}: settings nav`)
    assert.equal(probe.userDetails, 'User details', `${context}: user details section`)
    assert.equal(probe.logout, true, `${context}: logout present`)
    assert.equal(probe.deleteAccount, true, `${context}: delete account present`)
  },
  '/profile/settings': async ({ run, context }) => {
    const probe = await evalProbe(run, `(() => ({
      heading: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent.trim(),
      settingsSection: document.querySelector('h2#user-settings-section')?.textContent.trim(),
      labels: ['Default currency', 'Number of digits', 'Default Account Selection'].map((label) => [...document.querySelectorAll('label')].some((l) => l.textContent.trim() === label)),
      save: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Save Settings'),
      groups: !!document.querySelector('[aria-label="Account groups"], .v-expansion-panels'),
    }))()`)
    assert.equal(probe.heading, 'Profile', `${context}: settings keeps one profile heading`)
    assert.equal(probe.settingsSection, 'User Settings', `${context}: settings section`)
    assert.ok(probe.labels.every(Boolean), `${context}: settings fields labelled`)
    assert.equal(probe.save, true, `${context}: Save Settings action`)
  },
}

// Structural probe over one migrated family route: exactly one h1 in main
// (the WorkspacePage heading once the family is migrated), no page-level
// horizontal overflow, plus the family's behavior flow.
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
  // Give the lazy route chunk + async context bootstrap room before probing
  // (bounded: fall through to whatever rendered after 5s).
  await waitFor(run, `document.querySelectorAll('.v-main h1').length > 0 || document.querySelector('.v-main .legacy-page-heading, [data-testid="legacy-page-heading"]') !== null`, 5000).catch(() => {})
  await run(['wait', '300'])

  // agent-browser occasionally serves a command against a transient blank
  // automation tab right after a navigation (observed: the h1 wait above
  // already succeeded on the real page, the next eval lands on about:blank).
  // Re-eval briefly until the app origin is back before failing.
  let probe = null
  for (let attempt = 0; attempt < 4; attempt++) {
    probe = await evalProbe(
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
        bodyHead: document.body.innerText.slice(0, 80).split(String.fromCharCode(10)).join(' '),
      }
    })()`,
    )
    if (probe.path && probe.path !== 'blank' && probe.path !== '/') break
    await run(['open', `${appOrigin}${route}`])
    await run(['wait', '400'])
  }
  assert.equal(
    probe.headingCount,
    1,
    `${context}: ${route} renders exactly one h1 (got ${probe.headingCount}: ${probe.headingText}) at ${probe.path}; body head: ${probe.bodyHead}`,
  )
  assert.ok(probe.workspaceHeading, `${context}: ${route} heading is workspace-owned`)
  assert.equal(probe.pageOverflow, false, `${context}: ${route} has no page-level horizontal overflow`)

  if (familyFlows[route]) {
    // The nested child route chunk can lag one tick behind the parent's h1;
    // wait for the section headings before asserting family behavior.
    await waitFor(run, `document.querySelectorAll('.v-main h2').length > 0`, 8000).catch(() => {})
    await familyFlows[route]({ run, context })
    console.log(`PASS ${context} ${route} family flow`)
  }
  return probe
}


// Review-round rendered-state acceptance: populated / empty /
// filtered-empty / error per applicable family, with justified N/A entries
// recorded in the route review. The fixture server serves honest
// state-switched payloads (including GENUINE server-side search filtering,
// so filtered-empty is a real server response, not a client artifact).
export async function assertD5StatesFlow({ appOrigin, context, initScript, log, session, fixtureServer, registerSession }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const open = async (route, ready) => {
    await run(['open', `${appOrigin}${route}`])
    await waitFor(run, `document.querySelector('[data-testid="route-content"]') !== null`)
    await run(['wait', '500'])
    if (ready) await waitFor(run, ready, 8000).catch(() => {})
  }
  const textOf = (sel) => evalProbe(run, `document.querySelector('${sel}')?.textContent ?? document.body.innerText`)

  // --- EMPTY state -------------------------------------------------------
  fixtureServer.setD5State('empty')
  await open('/summary')
  let probe = await textOf('main')
  assert.ok(probe.includes('No account performance data'), `${context}: summary empty performance state`)
  assert.ok(probe.includes('No breakdown data'), `${context}: summary empty breakdown state`)
  probe = await evalProbe(run, `(() => { const sel = document.querySelector('[data-testid="performance-view-select"]'); return sel ? sel.classList.contains('v-input--disabled') || !!sel.querySelector('input[disabled]') : null })()`)
  assert.equal(probe, true, `${context}: summary period controls disabled for empty data`)

  for (const [route, marker] of [
    ['/database/brokers', 'Add Broker'],
    ['/database/accounts', 'Add Account'],
    ['/database/securities', 'Record Merger'],
  ]) {
    await open(route, `document.querySelectorAll('.v-data-table tbody tr').length >= 0 && document.querySelector('.v-data-table') !== null`)
    probe = await textOf('.v-data-table')
    assert.ok(probe.toLowerCase().includes('no data available'), `${context}: ${route} empty inventory state (${probe.slice(0, 40)})`)
    probe = await textOf('main')
    assert.ok(probe.includes(marker), `${context}: ${route} keeps its primary actions in the empty state`)
  }

  await open('/database/prices', `document.querySelector('.v-data-table') !== null`)
  probe = await textOf('.v-data-table')
  assert.ok(probe.includes('Apply Filters'), `${context}: prices empty state keeps its guided no-data text`)

  await open('/database/fx', `document.querySelector('.v-data-table') !== null`)
  probe = await evalProbe(run, `(() => ({ headers: [...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim()), addAction: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Add FX Rate') }))()`)
  assert.deepEqual(probe.headers, ['Date'], `${context}: fx empty pivot renders the Date column only`)
  assert.equal(probe.addAction, true, `${context}: fx keeps Add FX Rate in the empty state`)

  await run(['open', `${appOrigin}/summary`])
  await run(['wait', '600'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'd5-summary-empty.png')])
  console.log('CAPTURED d5-summary-empty.png')
  await run(['open', `${appOrigin}/database/brokers`])
  await run(['wait', '600'])
  await run(['screenshot', resolve(DESIGN_ASSETS, 'd5-brokers-empty.png')])
  console.log('CAPTURED d5-brokers-empty.png')

  // --- ERROR state (wait for each surface's actual failure message) ------
  fixtureServer.setD5State('error')
  await open('/summary')
  await waitFor(run, `document.body.innerText.includes('Unable to load part of the summary')`, 8000)
    .catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load part of the summary'), `${context}: summary error state`)
  for (const route of ['/database/brokers', '/database/accounts', '/database/securities']) {
    await open(route)
    await waitFor(run, `document.body.innerText.includes('Unable to load this table')`, 8000)
      .catch(() => {})
    probe = await textOf('main')
    assert.ok(probe.includes('Unable to load this table'), `${context}: ${route} error state with retry`)
  }
  await open('/database/prices')
  await waitFor(run, `document.body.innerText.includes('Unable to load prices or filters')`, 8000)
    .catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load prices or filters'), `${context}: prices error state`)
  await open('/database/fx')
  await waitFor(run, `document.body.innerText.includes('Unable to load exchange rates')`, 8000)
    .catch(() => {})
  probe = await textOf('main')
  assert.ok(probe.includes('Unable to load exchange rates'), `${context}: fx error state`)
  await open('/profile/settings')
  await waitFor(run, `document.body.innerText.includes('Failed to load settings')`, 8000)
    .catch(() => {})
  probe = await textOf('body')
  assert.ok(probe.includes('Failed to load settings'), `${context}: settings error state surfaces the failure`)

  // --- FILTERED-EMPTY (genuine server filtering on a no-match search) ----
  fixtureServer.setD5State('populated')
  const searchNoMatch = async (route) => {
    await open(route, `document.querySelector('.workspace-table-toolbar input') !== null`)
    await run(['eval', `(() => { const input = document.querySelector('.workspace-table-toolbar input'); input.value = 'zzz-no-match'; input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
    await run(['wait', '900'])
    const probe = await textOf('.v-data-table')
    assert.ok(probe.toLowerCase().includes('no data available'), `${context}: ${route} filtered-empty after a no-match search`)
  }
  await searchNoMatch('/database/brokers')
  await searchNoMatch('/database/accounts')
  await searchNoMatch('/database/securities')
  // The FX pivot searches pair codes.
  await open('/database/fx', `document.querySelector('.workspace-table-toolbar input') !== null`)
  await run(['eval', `(() => { const input = document.querySelector('.workspace-table-toolbar input'); input.value = 'zzz-no-match'; input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
  await run(['wait', '900'])
  probe = await evalProbe(run, `[...document.querySelectorAll('.v-data-table thead th')].map((th) => th.textContent.trim())`)
  assert.deepEqual(probe, ['Date'], `${context}: fx filtered-empty drops every pair column (no data rows)`)

  // --- LOGIN error state (public session; authenticated users never see
  // the form). The fixture answers 401 with invalid credentials; the error
  // summary must render readably.
  fixtureServer.setD5State('error')
  const loginSession = `d5-states-login-${process.pid}`
  registerSession(loginSession)
  const loginRun = (args) => runAgentBrowser({ args, context: `${context} login`, initScript: undefined, log, session: loginSession })
  await loginRun(['open', `${appOrigin}/login`])
  await loginRun(['wait', '400'])
  await loginRun(['eval', `(() => { const user = document.querySelector('input[autocomplete="username"]'); const pass = document.querySelector('input[autocomplete="current-password"]'); if (!user || !pass) throw new Error('login fields missing'); user.value = 'fixture-user'; user.dispatchEvent(new Event('input', { bubbles: true })); pass.value = 'wrong-password'; pass.dispatchEvent(new Event('input', { bubbles: true })); return true })()`])
  await loginRun(['eval', `(() => { document.querySelector('button[type="submit"]')?.click(); return true })()`])
  await loginRun(['wait', '--fn', `!!document.querySelector('[role="alert"], .v-alert') || document.body.innerText.toLowerCase().includes('invalid') || document.body.innerText.toLowerCase().includes('credential') || document.body.innerText.toLowerCase().includes('error')`, '--timeout', '8000'])
    .catch(() => {})
  const loginText = (await loginRun(['eval', 'document.body.innerText'])).result
  assert.ok(
    /invalid|credential|error|denied|failed/i.test(loginText),
    `${context}: login error state surfaces a readable error summary`,
  )
  assert.equal((await loginRun(['eval', 'location.pathname'])).result, '/login', `${context}: failed login stays on the login page`)

  fixtureServer.setD5State('populated')
  console.log(`PASS ${context} rendered states (empty/error/filtered-empty + login error)`)
}


// Review round 2 — mobile page-control containment (390px): the workspace
// page grid must constrain its single column to the viewport so headings/
// descriptions wrap and page controls stay inside the viewport and genuinely
// hittable. Bounds are checked per-element because body overflow-x:hidden
// clips ancestors without producing page scrollWidth overflow (the D3-era
// scrollWidth probe is blind to exactly this). Table overflow stays local:
// only page controls are asserted here, never the scrollable table body.
// Prices has no shared table toolbar: its page controls are the filter
// fields and Apply Filters, asserted through the 'filters' kind.
const MOBILE_CONTROL_SPECS = {
  '/database/brokers': { kind: 'shared', actions: ['Add Broker'] },
  '/database/accounts': { kind: 'shared', actions: ['Add Account'] },
  '/database/securities': { kind: 'shared', actions: ['Add Security', 'Record Merger'] },
  '/database/prices': { kind: 'filters', actions: ['Apply Filters', 'Add Price Entry', 'Import Prices'] },
  '/database/fx': { kind: 'shared', actions: ['Add FX Rate', 'Import FX Rates'] },
}

export async function assertMobilePageControlsFlow({ appOrigin, context, initScript, log, session }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  // This flow owns its viewport: the session may be at any size when it
  // starts, and every assertion below is meaningless unless the layout is
  // actually 390px wide. Restored to desktop at the end for the zoom phase.
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '300'])

  const PROBE = (spec) => `(() => {
    const withinViewportX = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
    const hit = (el) => { const b = el.getBoundingClientRect(); const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!h && (el.contains(h) || h === el) }
    const reachable = (el) => { el.scrollIntoView({ block: 'center' }); return withinViewportX(el) && hit(el) }
    const desc = document.querySelector('[data-testid="workspace-page-heading"]')?.parentElement?.querySelector('p')
    const actions = ${JSON.stringify(spec.actions)}.map((label) => {
      const el = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === label)
      return { label, present: !!el, contained: el ? withinViewportX(el) : false, reachable: el ? reachable(el) : false }
    })
    const tabs = [...document.querySelectorAll('[data-testid="database-nav"] a')]
    let search = null, rows = null, filterFields = []
    if (${JSON.stringify(spec.kind)} === 'shared') {
      search = document.querySelector('.workspace-table-toolbar__search')
      rows = document.querySelector('.workspace-table-toolbar__rows')
      if (search) search = { contained: withinViewportX(search), reachable: reachable(search) }
      if (rows) rows = { contained: withinViewportX(rows), reachable: reachable(rows) }
    } else {
      // Prices filter fields: locate each labelled v-input.
      for (const label of ['Asset Types', 'Accounts', 'Securities', 'Start Date', 'End Date']) {
        const labelEl = [...document.querySelectorAll('label')].find((l) => l.textContent.trim() === label)
        const field = labelEl?.closest('.v-input')
        filterFields.push({ label, present: !!field, contained: field ? withinViewportX(field) : false, reachable: field ? reachable(field) : false })
      }
    }
    return {
      viewport: innerWidth,
      descWidth: desc ? Math.round(desc.getBoundingClientRect().width) : null,
      search, rows, filterFields, actions,
      tabsReachable: tabs.map((t) => reachable(t)),
    }
  })()`

  const assertProbe = (route, probe, phase, kind) => {
    assert.ok(probe.descWidth !== null && probe.descWidth <= probe.viewport + 1,
      `${context}: ${route} ${phase}: page description wraps inside the viewport (width ${probe.descWidth} at ${probe.viewport}px)`)
    if (kind === 'shared') {
      assert.ok(probe.search && probe.search.contained && probe.search.reachable,
        `${context}: ${route} ${phase}: search control inside the viewport and hittable (${JSON.stringify(probe.search)})`)
      assert.ok(probe.rows && probe.rows.contained && probe.rows.reachable,
        `${context}: ${route} ${phase}: rows-per-page control inside the viewport and hittable (${JSON.stringify(probe.rows)})`)
    } else {
      for (const field of probe.filterFields) {
        assert.ok(field.present && field.contained && field.reachable,
          `${context}: ${route} ${phase}: filter field ${field.label} inside the viewport and hittable (${JSON.stringify(field)})`)
      }
    }
    for (const action of probe.actions) {
      assert.ok(action.present, `${context}: ${route} ${phase}: action ${action.label} present`)
      assert.ok(action.reachable, `${context}: ${route} ${phase}: action ${action.label} scrollable into view and hittable (${JSON.stringify(action)})`)
    }
    if (probe.tabsReachable.length) {
      assert.ok(probe.tabsReachable.every(Boolean),
        `${context}: ${route} ${phase}: every data-nav section reachable via its scroll group (${JSON.stringify(probe.tabsReachable)})`)
    }
  }

  // Fresh mobile load per family.
  for (const [route, spec] of Object.entries(MOBILE_CONTROL_SPECS)) {
    await run(['open', `${appOrigin}${route}`])
    await waitFor(run, `document.querySelector('.workspace-table-toolbar') !== null || [...document.querySelectorAll('label')].some((l) => l.textContent.trim() === 'Asset Types')`, 8000).catch(() => {})
    await run(['wait', '400'])
    const probe = await evalProbe(run, PROBE(spec))
    assertProbe(route, probe, 'fresh mobile load', spec.kind)
  }

  // Resize transitions on one representative family: desktop -> 390 -> desktop.
  await run(['open', `${appOrigin}/database/securities`])
  await waitFor(run, `document.querySelector('.workspace-table-toolbar') !== null`, 8000).catch(() => {})
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '300'])
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '300'])
  let probe = await evalProbe(run, PROBE(MOBILE_CONTROL_SPECS['/database/securities']))
  assertProbe('/database/securities', probe, 'desktop->390 transition', 'shared')
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '300'])
  probe = await evalProbe(run, PROBE(MOBILE_CONTROL_SPECS['/database/securities']))
  // At desktop every control must be back inside the (now wide) viewport.
  assert.ok(probe.descWidth !== null && probe.descWidth <= probe.viewport + 1,
    `${context}: /database/securities 390->desktop: description contained again`)
  for (const action of probe.actions) {
    assert.ok(action.present && action.reachable,
      `${context}: /database/securities 390->desktop: ${action.label} hittable again (${JSON.stringify(action)})`)
  }
  assert.ok(probe.search.reachable && probe.rows.reachable,
    `${context}: /database/securities 390->desktop: toolbar controls hittable again`)
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '200'])
  console.log(`PASS ${context} mobile page-control containment`)
}

// Native 200% zoom on a dense data route: dpr must be a real 2.0 (CDP key
// events, not CSS zoom), the primary action and the section heading must
// stay reachable, then the zoom resets.
export async function assertD5NativeZoomFlow({ appOrigin, context, initScript, log, session }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: `${context} cdp`, initScript, log, session })
  const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
  assert.ok(cdpUrl, `${context}: cdp url available`)

  const zoomTo = (percent) =>
    new Promise((resolveSpawn, rejectSpawn) => {
      const child = spawn(process.execPath, [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), appOrigin, String(percent)], { stdio: 'pipe' })
      let out = ''
      child.stdout.on('data', (chunk) => { out += chunk })
      child.stderr.on('data', (chunk) => { out += chunk })
      child.on('error', rejectSpawn)
      child.on('close', (code) => resolveSpawn({ code, out }))
    })

  await run(['open', `${appOrigin}/database/accounts`])
  await waitFor(run, `document.querySelectorAll('.v-data-table tbody tr').length > 0`)

  const zoomed = await zoomTo(200)
  assert.equal(zoomed.code, 0, `${context}: native 200% zoom must be dpr-verified (${zoomed.out.trim()})`)
  await run(['wait', '300'])
  const probe = await evalProbe(run, `(() => ({
    dpr: window.devicePixelRatio,
    heading: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent.trim(),
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }))()`)
  assert.ok(probe.dpr >= 1.9, `${context}: devicePixelRatio is a real browser zoom (${probe.dpr})`)
  assert.equal(probe.heading, 'Data', `${context}: heading survives zoom via the nested layout`)
  assert.equal(probe.overflow, false, `${context}: no page-level overflow at 200%`)
  // The primary create action stays genuinely reachable (scrollable into
  // view and elementFromPoint-hittable) at 200%.
  await run(['eval', `document.querySelector('[data-testid="add-account"]')?.scrollIntoView({ block: 'center' })`])
  await run(['wait', '200'])
  await hitTest(run, '[data-testid="add-account"]', `${context} Add Account at 200%`)

  const reset = await zoomTo(100)
  assert.equal(reset.code, 0, `${context}: zoom reset verified (${reset.out.trim()})`)
  console.log(`PASS ${context} native 200% zoom`)
}

// Captures from the rendered build: one per family + the public auth
// surface, named d5-* under docs/design/assets/frontend-workspace/.
export async function captureD5Screenshots({ appOrigin, context, initScript, log, session, registerSession }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const shotsDir = DESIGN_ASSETS
  const shot = (name) => run(['screenshot', resolve(shotsDir, name)])

  const capture = async (route, name, readySelector = '.workspace-page') => {
    await run(['open', `${appOrigin}${route}`])
    if (readySelector) await waitFor(run, `!!document.querySelector('${readySelector}')`, 10000)
    await run(['wait', '400'])
    // Verified captures: at mobile sizes assert page-control containment
    // IMMEDIATELY before shooting, so the image cannot silently show the
    // grid-blowout clipping this round fixed (the checked geometry is the
    // geometry in the frame).
    if (name.endsWith('-mobile.png')) {
      const probe = await evalProbe(run, `(() => {
        const withinViewportX = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
        const desc = document.querySelector('[data-testid="workspace-page-heading"]')?.parentElement?.querySelector('p')
        const buttons = [...document.querySelectorAll('button')]
          .filter((b) => ['Add Security', 'Record Merger', 'Add Broker', 'Add Account', 'Add Price Entry', 'Import Prices', 'Add FX Rate', 'Import FX Rates', 'Apply Filters'].includes(b.textContent.trim()))
          .map((b) => ({ label: b.textContent.trim(), contained: withinViewportX(b), inDoc: b.getBoundingClientRect().width > 0 }))
        return { viewport: innerWidth, descWidth: desc ? Math.round(desc.getBoundingClientRect().width) : null, buttons }
      })()`)
      assert.ok(probe.descWidth <= probe.viewport + 1,
        `${context}: capture ${name}: page description contained (${probe.descWidth}px at ${probe.viewport}px)`)
      for (const button of probe.buttons) {
        assert.ok(button.inDoc && button.contained,
          `${context}: capture ${name}: action ${button.label} inside the viewport before shooting (${JSON.stringify(button)})`)
      }
    }
    await shot(name)
    console.log(`CAPTURED ${name}`)
  }

  await run(['set', 'viewport', '1440', '1000'])
  await capture('/summary', 'd5-summary-single.png', '.account-performance-table')
  await openSelectByTestId(run, 'performance-view-select')
  await pickOverlayItem(run, 'Full history')
  await run(['wait', '200'])
  await shot('d5-summary-history.png')
  console.log('CAPTURED d5-summary-history.png')
  await capture('/database', 'd5-database-landing.png', '#database-landing')
  await capture('/database/brokers', 'd5-brokers-desktop.png', '#brokers-section')
  await capture('/database/accounts', 'd5-accounts-desktop.png', '#accounts-section')
  await capture('/database/securities', 'd5-securities-desktop.png', '#securities-section')
  await capture('/database/prices', 'd5-prices-desktop.png', '#prices-section')
  await capture('/database/fx', 'd5-fx-desktop.png', '#fx-section')
  await capture('/database/securities/1', 'd5-security-detail.png', '#security-basic')
  await capture('/profile', 'd5-profile.png', '#user-details-section')
  await capture('/profile/settings', 'd5-profile-settings.png', '#user-settings-section')
  await run(['set', 'viewport', '390', '844'])
  await capture('/database/securities', 'd5-securities-mobile.png', '#securities-section')
  await capture('/summary', 'd5-summary-mobile.png', '.account-performance-table')

  // Public auth surface on its own (unauthenticated) session.
  const authSession = `d5-auth-shots-${process.pid}`
  registerSession(authSession)
  const authRun = (args) => runAgentBrowser({ args, context: `${context} auth capture`, initScript: undefined, log, session: authSession })
  await authRun(['open', `${appOrigin}/login`])
  await authRun(['set', 'viewport', '390', '844'])
  await authRun(['wait', '400'])
  await authRun(['screenshot', resolve(shotsDir, 'd5-login-mobile.png')])
  console.log('CAPTURED d5-login-mobile.png')
}
