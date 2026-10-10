import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

/** Change a real mounted table's preset and effective date through the UI. */
export async function assertMountedDateFlow({
  context,
  initScript,
  log,
  session,
  fixtureServer,
  appOrigin,
}) {
  const run = (args) =>
    runAgentBrowser({ args, context, initScript, log, session })
  const evalP = async (expression) =>
    (await run(['eval', expression])).result
  async function click(role, name) {
    for (let attempt = 0; attempt < 12; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const ref = Object.entries(snapshot.refs).find(
        ([, item]) =>
          item.role === role && item.name.toLowerCase() === name.toLowerCase()
      )?.[0]
      if (ref) {
        try {
          await run([
            'click',
            role === 'combobox' && name === 'Year'
              ? '.workspace-table-toolbar .positions-year-select .v-field'
              : `@${ref}`,
          ])
          return
        } catch (error) {
          if (!String(error.message).includes('is covered by')) throw error
        }
      }
      await run(['wait', '100'])
    }
    assert.fail(`Missing clickable ${role} ${name}`)
  }

  await click('combobox', 'Year')
  await click('option', 'YTD')
  await run(['wait', '200'])
  const before = fixtureServer.requests.length
  const initialDate = await run([
    'get',
    'value',
    '.workspace-context input[type="date"]',
  ])
  assert.equal(initialDate.value, '2026-09-08')
  // The native date input exposes locale-specific segments. CLI fill types
  // plain text and leaves this input empty; real key presses edit each segment.
  for (const [part, keys] of [
    ['Year', ['ArrowDown']],
    ['Month', ['1', '2']],
    ['Day', ['3', '1']],
  ]) {
    const snapshot = await run(['snapshot', '-i', '-s', '.workspace-context'])
    const segment = Object.values(snapshot.refs).find(
      (item) => item.role === 'spinbutton' && item.name.includes(part)
    )
    assert.ok(segment, `Missing native date ${part} segment`)
    await click('spinbutton', segment.name)
    for (const key of keys) await run(['press', key])
  }
  const editedDate = await run([
    'get',
    'value',
    '.workspace-context input[type="date"]',
  ])
  assert.equal(editedDate.value, '2025-12-31')
  const filled = (
    await run([
      'eval',
      `({ value: document.querySelector('.workspace-context input[type="date"]')?.value, text: document.querySelector('.workspace-context')?.innerText })`,
    ])
  ).result
  await run(['press', 'Enter'])
  await run(['wait', '350'])

  const after = fixtureServer.requests.slice(before)
  const settings = after.filter(
    (request) =>
      request.actualMethod === 'POST' &&
      request.path === '/users/api/update_dashboard_settings/'
  )
  const refresh = after.filter(
    (request) =>
      request.actualMethod === 'POST' &&
      request.path === '/users/api/refresh-token/'
  )
  const positions = after.filter(
    (request) =>
      request.actualMethod === 'POST' &&
      request.path === '/open_positions/api/get_open_positions_table/'
  )
  const dialog = (
    await run([
      'eval',
      `({ value: document.querySelector('.workspace-context input[type="date"]')?.value, text: document.querySelector('.workspace-context')?.innerText })`,
    ])
  ).result
  assert.equal(
    settings.length,
    1,
    `one settings mutation must commit the new date: ${JSON.stringify({ filled, dialog, paths: after.map(({ actualMethod, path }) => ({ actualMethod, path })) })}`
  )
  assert.equal(settings[0].body.table_date, '2025-12-31')
  assert.equal(
    refresh.length,
    1,
    'date mutation must rotate the session token once'
  )
  assert.equal(refresh[0].body.effective_current_date, '2025-12-31')
  assert.equal(
    positions.length,
    1,
    `one resulting YTD table query expected: ${JSON.stringify(positions)}`
  )
  assert.deepEqual(
    {
      dateFrom: positions[0].body.dateFrom,
      dateTo: positions[0].body.dateTo,
      page: positions[0].body.page,
    },
    { dateFrom: '2025-01-01', dateTo: '2025-12-31', page: 1 }
  )
  const page = (
    await run([
      'eval',
      `({ path: location.pathname, date: document.querySelector('.workspace-context input[type="date"]')?.value ?? null })`,
    ])
  ).result
  assert.equal(page.path, '/open-positions')
  await log({
    context,
    before,
    settings,
    refresh,
    positions,
    page,
    status: 'passed',
  })
  // --- Task 1: the dashboard reconciles a persisted custom range when a
  // historical valuation date commits, through rendered controls only.
  // Custom From=2026-01-01/To=2026-10-09 persist; the valuation date then
  // commits as 2024-06-30 (From is later than the new effective date too).
  await run(['open', appOrigin + '/dashboard'])
  await run(['wait', '2500'])
  await run(['eval', 'performance.clearResourceTimings(); true'])

  // Persist a custom range through the rendered date-range menu. Its two
  // native date inputs are edited segment by segment with real key presses
  // (CLI fill leaves native date inputs empty).
  await click('button', '01 Jan 2026 \u2794 08 Sep 2026')
  await run(['wait', '600'])
  const setMenuDateByIndex = async (index, keys) => {
    const snapshot = await run(['snapshot', '-i', '-s', '.v-overlay--active'])
    const segments = Object.entries(snapshot.refs).filter(
      ([, item]) => item.role === 'spinbutton'
    )
    assert.ok(segments.length >= 3, 'menu date segments missing (' + segments.length + ')')
    const ordered = index === 0 ? segments.slice(0, 3) : segments.slice(3, 6)
    assert.ok(ordered.length === 3, 'menu date ' + index + ' segments missing')
    for (const refId of ordered.map(([refId]) => refId)) {
      await run(['click', '@' + refId])
    }
    for (const key of keys) await run(['press', key])
  }
  await setMenuDateByIndex(0, ['2', '0', '2', '6', '0', '1', '0', '1'])
  await setMenuDateByIndex(1, ['2', '0', '2', '6', '1', '0', '0', '9'])
  await click('button', 'Apply')
  await run(['wait', '800'])

  // Commit the historical valuation date through the rendered header control.
  const navCountBefore = await evalP(
    "performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).length"
  )
  await click('spinbutton', 'Year')
  for (const key of ['2', '0', '2', '4']) await run(['press', key])
  const monthSnapshot = await run(['snapshot', '-i', '-s', '.workspace-context'])
  const monthSegment = Object.entries(monthSnapshot.refs).find(
    ([, item]) => item.role === 'spinbutton' && item.name.includes('Month')
  )
  assert.ok(monthSegment, 'header date Month segment missing')
  await run(['click', '@' + monthSegment[0]])
  for (const key of ['0', '6']) await run(['press', key])
  const daySnapshot = await run(['snapshot', '-i', '-s', '.workspace-context'])
  const daySegment = Object.entries(daySnapshot.refs).find(
    ([, item]) => item.role === 'spinbutton' && item.name.includes('Day')
  )
  assert.ok(daySegment, 'header date Day segment missing')
  await run(['click', '@' + daySegment[0]])
  for (const key of ['3', '0']) await run(['press', key])
  await run(['press', 'Enter'])
  await run(['wait', '2500'])

  const navCountAfter = await evalP(
    "performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).length"
  )
  assert.equal(
    navCountAfter - navCountBefore,
    1,
    'exactly one accepted NAV refresh expected after the valuation-date change (' + navCountBefore + ' -> ' + navCountAfter + ')'
  )
  const lastNav = await evalP(
    "decodeURIComponent(performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).pop() || '')"
  )
  assert.ok(lastNav.includes('dateFrom=2024-06-30'), 'outgoing request From not clamped: ' + lastNav)
  assert.ok(lastNav.includes('dateTo=2024-06-30'), 'outgoing request To not clamped: ' + lastNav)
  const activatorText = await evalP(
    "[...document.querySelectorAll('button')].find((b) => b.textContent.includes('\u2794'))?.textContent.trim() ?? null"
  )
  assert.equal(activatorText, '30 Jun 2024 \u2794 30 Jun 2024', 'displayed range must reconcile: ' + activatorText)
  await log({
    context,
    dashboardReconciliation: { navCountBefore, navCountAfter, lastNav, activatorText },
    status: 'passed',
  })

  return {
    settings: settings.length,
    refresh: refresh.length,
    positions: positions.length,
    range: positions[0].body,
  }
}
