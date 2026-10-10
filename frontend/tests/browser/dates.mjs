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
  const waitFor = (fn, timeout = 15000) =>
    new Promise((resolvePromise, rejectPromise) => {
      const startedAt = Date.now()
      const tick = async () => {
        try {
          if ((await evalP(fn)) === true) {
            resolvePromise()
            return
          }
        } catch {
          /* retried until the timeout */
        }
        if (Date.now() - startedAt > timeout) {
          rejectPromise(new Error('waitFor timeout: ' + fn))
          return
        }
        setTimeout(tick, 250)
      }
      tick()
    })
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
  // Every intermediate valid date (2025-09-08, 2025-01-08, 2025-01-03) fires
  // input+change on the field; the keyboard guard must defer all of them so
  // only the Enter commit reaches the settings endpoint.
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

  // Persist a custom range through the rendered date-range menu, following
  // the charts-c5 harness pattern: settle the chart card first (a late
  // widget re-render replaces the card's menu and would close one opened
  // too early), open the menu through the real activator button, set the
  // two native date inputs with real input/change events, then Apply.
  await waitFor(
    `document.querySelector('[data-testid="nav-chart"]') !== null && document.querySelector('[data-testid="nav-chart"] canvas') !== null && document.querySelector('[data-testid="nav-error"]') === null`
  )
  await run(['eval', `(() => {
    const activator = [...document.querySelectorAll('[data-testid="nav-chart"] button')].find((button) => button.querySelector('svg'))
    if (!activator) throw new Error('date-range activator missing')
    activator.click()
    return true
  })()`])
  await waitFor(`document.querySelector('.v-overlay--active input[type="date"]') !== null`)
  const setMenuDate = async (index, value) => {
    await run(['eval', `(() => {
      const inputs = [...document.querySelectorAll('.v-overlay--active input[type="date"]')]
      const input = inputs[${index}]
      if (!input) throw new Error('menu date input ${index} missing')
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
      setter.call(input, '${value}')
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      return input.value
    })()`])
  }
  await setMenuDate(0, '2026-01-01')
  await setMenuDate(1, '2026-10-09')
  await run(['eval', `(() => {
    const apply = [...document.querySelectorAll('.v-overlay--active button')].find((button) => button.textContent.trim() === 'Apply')
    if (!apply) throw new Error('range Apply button missing')
    apply.click()
    return true
  })()`])
  await run(['wait', '800'])

  // Commit the historical valuation date through the rendered header control.
  const navCountBefore = await evalP(
    "performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).length"
  )
  const yearSnapshot = await run(['snapshot', '-i', '-s', '.workspace-context'])
  const yearSegment = Object.entries(yearSnapshot.refs).find(
    ([, item]) => item.role === 'spinbutton' && item.name.includes('Year')
  )
  assert.ok(yearSegment, 'header date Year segment missing')
  await run(['click', '@' + yearSegment[0]])
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
  // Calendar-picker path: selecting a date in the browser picker fires
  // input+change on the field without any keydown, so the commit is
  // immediate. Dispatching the same events on the real rendered field (after
  // the typed 2024-06-30 commit above) must produce exactly one settings
  // mutation and one accepted NAV refresh for the picked date.
  const pickerBefore = fixtureServer.requests.length
  const navPickerBefore = await evalP(
    "performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).length"
  )
  await evalP("(() => { const el = document.querySelector('.workspace-context input[type=\"date\"]'); el.value = '2024-06-29'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); return el.value })()")
  await run(['wait', '2500'])
  const pickerPosts = fixtureServer.requests
    .slice(pickerBefore)
    .filter((request) => request.actualMethod === 'POST' && request.path === '/users/api/update_dashboard_settings/')
  assert.equal(
    pickerPosts.length,
    1,
    'a picker change without keydown must commit exactly once: ' + JSON.stringify(fixtureServer.requests.slice(pickerBefore).map(({ actualMethod, path }) => actualMethod + ' ' + path))
  )
  assert.equal(pickerPosts[0].body.table_date, '2024-06-29')
  const navPickerAfter = await evalP(
    "performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).length"
  )
  assert.equal(
    navPickerAfter - navPickerBefore,
    1,
    'exactly one accepted NAV refresh expected after the picker commit (' + navPickerBefore + ' -> ' + navPickerAfter + ')'
  )
  const pickerNav = await evalP(
    "decodeURIComponent(performance.getEntriesByType('resource').map((e) => e.name).filter((n) => n.includes('get-nav-chart-data')).pop() || '')"
  )
  assert.ok(pickerNav.includes('dateFrom=2024-06-29'), 'picker commit did not refresh NAV: ' + pickerNav)
  await log({
    context,
    dashboardReconciliation: { navCountBefore, navCountAfter, lastNav, activatorText },
    pickerCommit: { pickerPosts: pickerPosts.length, pickerNav },
    status: 'passed',
  })

  return {
    settings: settings.length,
    refresh: refresh.length,
    positions: positions.length,
    range: positions[0].body,
  }
}
