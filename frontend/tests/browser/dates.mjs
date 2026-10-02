import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

/** Change a real mounted table's preset and effective date through the UI. */
export async function assertMountedDateFlow({
  context,
  initScript,
  log,
  session,
  fixtureServer,
}) {
  const run = (args) =>
    runAgentBrowser({ args, context, initScript, log, session })
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
  return {
    settings: settings.length,
    refresh: refresh.length,
    positions: positions.length,
    range: positions[0].body,
  }
}
