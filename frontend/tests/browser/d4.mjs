import assert from 'node:assert/strict'
import { resolve } from 'node:path'

import { runAgentBrowser } from './protocol.mjs'
import { d4OpenRows } from './d4-datasets.mjs'

// D4 rendered acceptance: preset switching, grouped chooser persistence,
// server-owned order, hidden sort, semantics (caption/colgroup/scope/aria-
// sort/headers associations), key-based pinning and footer alignment under
// scrolling, exact transaction confirmation lifecycle, and the seven named
// captures. All interactions run against complete synthetic fixtures.

const D4_OPEN_FIRST_ROW = d4OpenRows[0].name

const evalProbe = async (run, expression) => {
  const data = await run(['eval', expression])
  return data.result
}

const waitFor = (run, fn, timeout = 8000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const openViewSelect = async (run) => {
  await run(['eval', `(() => { const el = document.querySelector('[data-testid="positions-view-select"]'); el.querySelector('.v-field')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); el.querySelector('.v-field')?.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true })()`])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active .v-list-item').length > 0`)
}

const pickViewItem = async (run, label) => {
  await openViewSelect(run)
  await run(['eval', `(() => { const item = [...document.querySelectorAll('.v-overlay--active .v-list-item')].find(el => el.textContent.trim().startsWith('${label}')); if (!item) throw new Error('view item ${label} missing'); item.click(); return true })()`])
  await run(['wait', '150'])
  await run(['wait', '--fn', `document.querySelector('.v-overlay--active .v-list-item') === null`])
}

export async function assertD4TablesFlow({ appOrigin, context, initScript, log, session, fixtureServer }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })

  await run(['open', `${appOrigin}/open-positions`])
  await waitFor(run, `document.querySelectorAll('.positions-table tbody tr').length > 1`)

  // --- Overview semantics + server order ---------------------------------
  let probe = await evalProbe(run, `(() => {
    const table = document.querySelector('.positions-table')
    const caption = table.querySelector('table caption')
    const rows = table.querySelectorAll('tbody tr')
    return {
      caption: caption?.textContent?.trim() ?? null,
      headerRows: table.querySelectorAll('thead tr').length,
      leafCount: table.querySelectorAll('thead th[data-leaf-key]').length,
      bands: [...table.querySelectorAll('thead th.positions-group-band')].map(el => el.textContent.trim()),
      firstRowName: rows[0]?.querySelector('th[scope="row"]')?.textContent?.trim() ?? null,
      rowHeaderScope: !!rows[0]?.querySelector('th[scope="row"][data-leaf-key="name"]'),
      cellAssociation: rows[0]?.querySelector('td[data-leaf-key="entry_value"]')?.getAttribute('headers'),
      glossaryButtons: table.querySelectorAll('button.positions-glossary').length,
      glossaryLabel: table.querySelector('th[data-leaf-key="entry_value"] button.positions-glossary')?.getAttribute('aria-label') ?? null,
      colgroup: table.querySelectorAll('colgroup').length,
      cols: [...table.querySelectorAll('colgroup col[data-group]')].map(col => col.getAttribute('data-group')),
    }
  })()`, context)
  assert.equal(probe.caption, 'Open Positions — Overview view', `${context}: caption`)
  assert.equal(probe.headerRows, 1, `${context}: Overview is one structural header row`)
  assert.equal(probe.leafCount, 8, `${context}: Overview leaf count`)
  assert.deepEqual(probe.bands, [], `${context}: Overview has no bands`)
  // The fixture server ignores the requested sort: displayed order must be
  // exactly the server's shuffled order.
  assert.ok((probe.firstRowName ?? '').startsWith(D4_OPEN_FIRST_ROW), `${context}: server-owned display order (${probe.firstRowName})`)
  assert.equal(probe.rowHeaderScope, true, `${context}: Security row header`)
  assert.equal(probe.cellAssociation, 'open-positions-entry_value', `${context}: cell header association`)
  assert.ok(probe.glossaryButtons >= 5, `${context}: glossary triggers present`)
  assert.match(probe.glossaryLabel ?? '', /Entry value.*reporting currency \(USD\)/, `${context}: currency-aware glossary label`)

  // --- aria-sort cycling ---------------------------------------------------
  await run(['eval', `document.querySelector('.positions-table th[data-leaf-key="entry_value"]').click()`])
  await run(['wait', '150'])
  probe = await evalProbe(run, `document.querySelector('.positions-table th[aria-sort]')?.getAttribute('aria-sort')`, context)
  assert.equal(probe, 'ascending', `${context}: aria-sort ascending`)
  await run(['eval', `document.querySelector('.positions-table th[data-leaf-key="entry_value"]').click()`])
  await run(['wait', '150'])
  probe = await evalProbe(run, `document.querySelector('.positions-table th[aria-sort]')?.getAttribute('aria-sort')`, context)
  assert.equal(probe, 'descending', `${context}: aria-sort descending`)
  const lastPositionRequest = () => fixtureServer.d4.positionRequests.at(-1)
  assert.equal(lastPositionRequest().body.sortBy.key, 'entry_value', `${context}: sort param server-owned`)

  // --- Full ledger: bands, colgroup, pinning, footer alignment ------------
  await pickViewItem(run, 'Full ledger')
  probe = await evalProbe(run, `(() => {
    const table = document.querySelector('.positions-table')
    const bands = [...table.querySelectorAll('thead th.positions-group-band')]
    const totals = table.querySelectorAll('tfoot tr')[0]
    const alignUnderLeaf = ['entry_value', 'irr', 'current_value'].map((key) => {
      const th = table.querySelector(\`thead th[data-leaf-key="\${key}"]\`)
      const td = totals.querySelector(\`td[data-leaf-key="\${key}"]\`)
      return { key, thLeft: Math.round(th.getBoundingClientRect().left), tdLeft: Math.round(td.getBoundingClientRect().left) }
    })
    return {
      headerRows: table.querySelectorAll('thead tr').length,
      leafCount: table.querySelectorAll('thead th[data-leaf-key]').length,
      bands: bands.map(el => el.textContent.trim()),
      bandScopes: bands.map(el => el.getAttribute('scope')),
      cols: [...table.querySelectorAll('colgroup col[data-group]')].map(col => col.getAttribute('data-group')),
      typePin: table.querySelector('thead th[data-leaf-key="type"]')?.className.includes('col-pin-1'),
      namePin: table.querySelector('thead th[data-leaf-key="name"]')?.className.includes('col-pin-2'),
      currencyPinned: table.querySelector('thead th[data-leaf-key="currency"]')?.className.includes('col-pin') ?? false,
      alignUnderLeaf,
    }
  })()`, context)
  assert.equal(probe.headerRows, 2, `${context}: Full ledger has two header rows`)
  assert.equal(probe.leafCount, 20, `${context}: all 20 leaves reachable`)
  assert.deepEqual(probe.bands, ['Identity', 'Entry', 'Current', 'Performance'], `${context}: band labels`)
  assert.deepEqual(probe.bandScopes, ['colgroup', 'colgroup', 'colgroup', 'colgroup'], `${context}: band scopes`)
  assert.deepEqual(probe.cols, ['identity', 'entry', 'current', 'performance'], `${context}: colgroup groups`)
  assert.equal(probe.typePin, true, `${context}: Type pinned by key`)
  assert.equal(probe.namePin, true, `${context}: Security pinned by key`)
  assert.equal(probe.currencyPinned, false, `${context}: Currency never pinned`)
  for (const pair of probe.alignUnderLeaf) {
    assert.equal(pair.tdLeft, pair.thLeft, `${context}: footer cell under its leaf (${pair.key})`)
  }

  // --- Sticky identity + header tiers during scrolling --------------------
  await run(['eval', `(() => {
    const wrapper = document.querySelector('.positions-table .v-table__wrapper')
    wrapper.scrollLeft = wrapper.scrollWidth
    wrapper.scrollTop = 240
    return { scrollable: wrapper.scrollWidth > wrapper.clientWidth }
  })()`])
  await run(['wait', '200'])
  probe = await evalProbe(run, `(() => {
    const table = document.querySelector('.positions-table')
    const wrapper = table.querySelector('.v-table__wrapper')
    const appbar = document.querySelector('.v-app-bar')
    const type = table.querySelector('tbody td[data-leaf-key="type"]')
    const name = table.querySelector('tbody th[data-leaf-key="name"]')
    const bandRow = table.querySelectorAll('thead tr')[0]
    const leafRow = table.querySelectorAll('thead tr')[1]
    const totalsRow = table.querySelectorAll('tfoot tr')[0]
    const r = (el) => el.getBoundingClientRect()
    return {
      horizontallyScrollable: wrapper.scrollWidth > wrapper.clientWidth,
      wrapperLeft: Math.round(r(wrapper).left),
      typeLeft: Math.round(r(type).left),
      typeWidth: Math.round(r(type).width),
      nameLeft: Math.round(r(name).left),
      typeSticky: Math.abs(r(type).left - r(wrapper).left) <= 2,
      nameOffset: Math.round(r(name).left - r(wrapper).left),
      bandVisible: r(bandRow).bottom > (appbar ? r(appbar).bottom - 1 : 0) && r(bandRow).height > 0,
      leafRowVisible: r(leafRow).bottom >= r(bandRow).top - 1,
      totalsVisible: r(totalsRow).height > 0,
      wrapperLabel: wrapper.getAttribute('aria-label'),
      wrapperFocusable: wrapper.getAttribute('tabindex') === '0',
    }
  })()`, context)
  assert.equal(probe.horizontallyScrollable, true, `${context}: full ledger scrolls horizontally`)
  assert.equal(probe.typeSticky, true, `${context}: Type sticks at the scroll edge under horizontal scroll`)
  assert.ok(probe.nameOffset > 0 && probe.nameOffset < 400, `${context}: Security sticks inside the identity pair`)
  assert.ok(Math.abs(probe.nameOffset - probe.typeWidth) <= 2, `${context}: Security offset equals the measured Type width (${probe.nameOffset} vs ${probe.typeWidth})`)
  assert.equal(probe.bandVisible, true, `${context}: band tier stays visible below the app bar`)
  assert.equal(probe.leafRowVisible, true, `${context}: both header tiers stay together`)
  assert.match(probe.wrapperLabel ?? '', /Open Positions table, scrollable/, `${context}: named scroll region`)
  assert.equal(probe.wrapperFocusable, true, `${context}: keyboard-reachable scroll region`)
  await run(['eval', `document.querySelector('.positions-table .v-table__wrapper').scrollLeft = 0`])

  // --- Grouped chooser: repeated changes before Done, persistence ---------
  await run(['eval', `document.querySelector('.positions-workspace button[aria-label="Show or hide columns"]').click()`])
  await waitFor(run, `document.querySelector('.v-overlay--active .positions-columns-menu') !== null`)
  probe = await evalProbe(run, `(() => {
    const menu = document.querySelector('.v-overlay--active .positions-columns-menu')
    return {
      subheaders: [...menu.querySelectorAll('.v-list-subheader')].map(el => el.textContent.trim()),
      hasEntryPrice: !!menu.querySelector('[data-testid="column-entry_price"]'),
      nameDisabled: (menu.querySelector('[data-testid="column-name"] input') ?? {}).disabled,
      done: !!menu.querySelector('[data-testid="columns-done"]'),
    }
  })()`, context)
  assert.deepEqual(probe.subheaders, ['Identity', 'Entry', 'Current', 'Performance'], `${context}: chooser grouped by lifecycle`)
  assert.equal(probe.hasEntryPrice, true, `${context}: qualified chooser entries`)
  assert.equal(probe.nameDisabled, true, `${context}: Security locked in chooser`)
  assert.equal(probe.done, true, `${context}: explicit Done`)
  // Two repeated toggles while the menu stays open.
  for (const key of ['currency', 'commission']) {
    await run(['eval', `document.querySelector('.v-overlay--active [data-testid="column-${key}"] input').click()`])
    await run(['wait', '150'])
    const stillOpen = await evalProbe(run, `!!document.querySelector('.v-overlay--active .positions-columns-menu')`, context)
    assert.equal(stillOpen, true, `${context}: chooser stays open for repeated choices (${key})`)
  }
  await run(['eval', `document.querySelector('.v-overlay--active [data-testid="columns-done"]').click()`])
  await waitFor(run, `document.querySelector('.v-overlay--active .positions-columns-menu') === null`)
  probe = await evalProbe(run, `(() => ({ keys: [...document.querySelectorAll('.positions-table thead th[data-leaf-key]')].map(th => th.getAttribute('data-leaf-key')), saved: localStorage.getItem('positionsTableView.v1.u1.open-positions') }))()`, context)
  assert.equal(probe.keys.length, 18, `${context}: custom view applied (20 - currency - commission)`)
  assert.ok(!probe.keys.includes('currency') && !probe.keys.includes('commission'), `${context}: hidden leaves absent`)
  assert.ok(probe.saved.includes('"custom"'), `${context}: custom preset persisted per user/table`)

  // Route away and back: the saved view survives navigation.
  await run(['open', `${appOrigin}/dashboard`])
  await run(['wait', '400'])
  await run(['open', `${appOrigin}/open-positions`])
  await waitFor(run, `document.querySelectorAll('.positions-table tbody tr').length > 1`)
  probe = await evalProbe(run, `(() => ({ keys: [...document.querySelectorAll('.positions-table thead th[data-leaf-key]')].map(th => th.getAttribute('data-leaf-key')), caption: document.querySelector('.positions-table table caption')?.textContent?.trim() }))()`, context)
  assert.equal(probe.keys.length, 18, `${context}: saved custom view restored on route return`)
  assert.equal(probe.caption, 'Open Positions — Custom view', `${context}: caption names the restored view`)

  // Resize never overwrites the saved choice.
  await run(['set', 'viewport', '1024', '768'])
  await run(['wait', '300'])
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '300'])
  probe = await evalProbe(run, `(() => ({ keys: [...document.querySelectorAll('.positions-table thead th[data-leaf-key]')].map(th => th.getAttribute('data-leaf-key')), saved: localStorage.getItem('positionsTableView.v1.u1.open-positions') }))()`, context)
  assert.equal(probe.keys.length, 18, `${context}: resize preserved the saved view`)
  assert.ok(probe.saved.includes('"custom"'), `${context}: resize never mutated storage`)

  // --- Hidden active sort + Clear sort ------------------------------------
  await pickViewItem(run, 'Entry & valuation')
  await run(['eval', `document.querySelector('.positions-table th[data-leaf-key="entry_price"]').click()`])
  await run(['wait', '400'])
  await pickViewItem(run, 'Overview')
  probe = await evalProbe(run, `(() => {
    const summary = document.querySelector('[data-testid="hidden-sort-summary"]')
    return {
      present: !!summary,
      text: summary?.textContent?.replace(/\\s+/g, ' ').trim() ?? null,
      clear: !!document.querySelector('[data-testid="clear-sort"]'),
    }
  })()`, context)
  assert.equal(probe.present, true, `${context}: hidden sort summary visible`)
  assert.match(probe.text ?? '', /Sorted by Entry price — ascending/, `${context}: hidden sort named with full title`)
  assert.equal(fixtureServer.d4.positionRequests.at(-1).body.sortBy.key, 'entry_price', `${context}: hiding the column kept the server sort`)
  await run(['eval', `document.querySelector('[data-testid="clear-sort"]').click()`])
  await run(['wait', '400'])
  probe = await evalProbe(run, `!!document.querySelector('[data-testid="hidden-sort-summary"]')`, context)
  assert.equal(probe, false, `${context}: Clear sort removes the summary`)
  assert.deepEqual(fixtureServer.d4.positionRequests.at(-1).body.sortBy, {}, `${context}: Clear sort clears the server sort`)

  // --- Server pages: rows-per-page + page 2 -------------------------------
  await run(['eval', `(() => { const el = document.querySelector('.workspace-table-toolbar__rows'); el.querySelector('.v-field')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); el.querySelector('.v-field')?.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true })()`])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active .v-list-item').length > 0`)
  await run(['eval', `(() => { const item = [...document.querySelectorAll('.v-overlay--active .v-list-item')].find(el => el.textContent.trim() === '10'); item.click(); return true })()`])
  await run(['wait', '600'])
  probe = await evalProbe(run, `document.querySelectorAll('.positions-table tbody tr').length`, context)
  assert.equal(probe, 10, `${context}: rows-per-page reaches the server (page 1 has 10 rows)`)
  await run(['eval', `(() => { const pages = [...document.querySelectorAll('.v-pagination button')]; const second = pages.find(b => b.textContent.trim() === '2'); second.click(); return true })()`])
  await run(['wait', '600'])
  probe = await evalProbe(run, `(() => ({
    rows: document.querySelectorAll('.positions-table tbody tr').length,
    firstName: document.querySelector('.positions-table tbody tr th[scope="row"]')?.textContent?.trim(),
  }))()`, context)
  assert.equal(probe.rows, 2, `${context}: server page 2 renders its own rows`)
  assert.ok((probe.firstName ?? '').startsWith(d4OpenRows[10].name), `${context}: page 2 shows the server's page-2 order (${probe.firstName})`)

  // --- Reporting currency reactivity --------------------------------------
  // The committed reporting currency is changed through the context strip's
  // own Reporting currency select (existing context-change flow).
  await run(['eval', `(() => { const strip = document.querySelector('.workspace-context-settings'); const currency = [...strip.querySelectorAll('.v-select')].find(el => el.innerText.includes('Reporting currency')); currency.querySelector('.v-field')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); currency.querySelector('.v-field')?.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true })()`])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active .v-list-item').length > 0`)
  await run(['eval', `(() => { const item = [...document.querySelectorAll('.v-overlay--active .v-list-item')].find(el => /euro/i.test(el.textContent)); if (!item) throw new Error('Euro currency choice missing'); item.click(); return true })()`])
  await run(['wait', '1500'])
  await run(['open', `${appOrigin}/open-positions`])
  await waitFor(run, `document.querySelectorAll('.positions-table tbody tr').length > 1`)
  await pickViewItem(run, 'Entry & valuation')
  await waitFor(run, `document.querySelector('.positions-table th[data-leaf-key="current_price"]') !== null`)
  probe = await evalProbe(run, `(() => {
    const label = document.querySelector('.positions-table th[data-leaf-key="entry_value"] button.positions-glossary')?.getAttribute('aria-label')
    const price = document.querySelector('.positions-table th[data-leaf-key="current_price"] button.positions-glossary')?.getAttribute('aria-label')
    return { label, price }
  })()`, context)
  assert.match(probe.label ?? '', /reporting currency \(EUR\)/, `${context}: money units react to the committed reporting currency`)
  assert.match(probe.price ?? '', /security's trading currency/i, `${context}: instrument prices keep their unit meaning`)

  // Restore USD for the remaining checks.
  await run(['eval', `localStorage.setItem('positionsTableView.v1.u1.open-positions', JSON.stringify({ version: 1, preset: 'overview', visibleKeys: [] }))`])
  await log({ context, status: 'd4 tables flow passed' })
  console.log('PASS d4 tables flow')
}

export async function assertD4TransactionsFlow({ appOrigin, context, initScript, log, session, fixtureServer }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const dialogText = () => evalProbe(run, `document.querySelector('.v-overlay--active[role="dialog"]')?.innerText?.replace(/\\s+/g, ' ') ?? null`, context)

  await run(['open', `${appOrigin}/transactions`])
  await waitFor(run, `document.querySelectorAll('tbody button[aria-label^="Delete"]').length >= 4`)

  // --- Action hierarchy ---------------------------------------------------
  let probe = await evalProbe(run, `(() => ({
    add: !!document.querySelector('[data-action="add-transaction"]'),
    importBtn: !!document.querySelector('[data-action="import-transactions"]'),
    overflow: !!document.querySelector('button[aria-label="More actions"]'),
    deleteLabels: [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].map(b => b.getAttribute('aria-label')).slice(0, 2),
  }))()`, context)
  assert.equal(probe.add, true, `${context}: primary Add transaction`)
  assert.equal(probe.importBtn, true, `${context}: secondary Import transactions`)
  assert.equal(probe.overflow, true, `${context}: overflow control`)
  assert.match(probe.deleteLabels.join(' | '), /08-Sep-26/, `${context}: row controls named with dates`)

  await run(['eval', `document.querySelector('button[aria-label="More actions"]').click()`])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active [data-action]').length === 3`)
  probe = await evalProbe(run, `[...document.querySelectorAll('.v-overlay--active [data-action]')].map(el => el.getAttribute('data-action'))`, context)
  assert.deepEqual(probe, ['add-fx-transaction', 'transfer-asset', 'record-merger'], `${context}: overflow hierarchy`)
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  // Keyboard: Enter on the focused overflow activator opens the menu.
  await run(['eval', `document.querySelector('button[aria-label="More actions"]').focus()`])
  await run(['press', 'Enter'])
  await waitFor(run, `document.querySelectorAll('.v-overlay--active [data-action]').length === 3`)
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  // --- Delete regular_5: identity, Cancel focus, Escape return ------------
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].find(b => b.getAttribute('aria-label').includes('ACME Corp')); btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]') !== null`)
  probe = await evalProbe(run, `(() => ({
    text: document.querySelector('.v-overlay--active[role="dialog"]').innerText.replace(/\\s+/g, ' '),
    focusIsCancel: document.activeElement?.closest('[data-testid="confirm-cancel"]') !== null,
    confirmDisabled: document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').disabled,
  }))()`, context)
  assert.match(probe.text, /Delete transaction/, `${context}: confirmation title`)
  assert.match(probe.text, /ACME Corp/, `${context}: exact security identity`)
  assert.match(probe.text, /\(\$1,215\.00\) USD/, `${context}: displayed amount with currency`)
  assert.equal(probe.focusIsCancel, true, `${context}: initial focus on Cancel`)
  assert.equal(probe.confirmDisabled, false, `${context}: confirm enabled when the list row is sufficient`)
  assert.ok(!fixtureServer.d4.mutations.some((m) => m.path === '/transactions/api/5/'), `${context}: no detail request needed`)

  await run(['press', 'Escape'])
  await run(['wait', '300'])
  probe = await evalProbe(run, `(() => ({
    dialogGone: document.querySelector('.v-overlay--active[role="dialog"]') === null,
    focusBackOnRow: (document.activeElement?.getAttribute('aria-label') ?? '').includes('ACME Corp'),
  }))()`, context)
  assert.equal(probe.dialogGone, true, `${context}: Escape cancels`)
  assert.equal(probe.focusBackOnRow, true, `${context}: focus returns to the invoking row control`)

  // --- Rejected deletion retains subject/error; retry deletes once --------
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].find(b => b.getAttribute('aria-label').includes('ACME Corp')); btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]') !== null`)
  await run(['eval', `document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').click()`])
  await run(['wait', '500'])
  probe = await evalProbe(run, `(() => ({
    stillOpen: !!document.querySelector('.v-overlay--active[role="dialog"]'),
    text: document.querySelector('.v-overlay--active[role="dialog"]')?.innerText.replace(/\\s+/g, ' '),
}))()`, context)
  assert.equal(probe.stillOpen, true, `${context}: rejected deletion keeps the dialog open`)
  assert.match(probe.text ?? '', /ACME Corp/, `${context}: subject retained after rejection`)
  assert.match(probe.text ?? '', /could not be deleted/i, `${context}: inline error after rejection`)
  await run(['eval', `document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').click()`])
  await run(['wait', '600'])
  probe = await evalProbe(run, `(() => ({
    dialogGone: document.querySelector('.v-overlay--active[role="dialog"]') === null,
    rows: document.querySelectorAll('tbody button[aria-label^="Delete"]').length,
    focusFallback: (document.activeElement?.getAttribute('data-action') ?? document.activeElement?.textContent ?? ''),
  }))()`, context)
  assert.equal(probe.dialogGone, true, `${context}: successful retry closes`)
  assert.equal(probe.rows, 3, `${context}: deleted row removed after refresh`)
  const deletes5 = fixtureServer.d4.mutations.filter((m) => m.method === 'DELETE' && m.path === '/transactions/api/5/')
  assert.equal(deletes5.length, 2, `${context}: exactly two attempts (one rejection, one success), saw ${JSON.stringify(fixtureServer.d4.mutations)}`)

  // Focus fallback: the invoking row is gone, so a meaningful action got it.
  assert.match(probe.focusFallback, /add transaction/i, `${context}: focus falls back to the primary action`)

  // --- fx_5 with the same numeric id deletes through its own endpoint -----
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].find(b => b.getAttribute('aria-label').includes('FX transaction on 01-Sep-26')); btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]') !== null`)
  probe = await dialogText()
  assert.match(probe ?? '', /01-Sep-26/, `${context}: FX subject identity`)
  assert.match(probe ?? '', /\(€1,000\.00\) EUR/, `${context}: FX from amount with currency`)
  await run(['eval', `document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').click()`])
  await run(['wait', '500'])
  assert.ok(fixtureServer.d4.mutations.some((m) => m.method === 'DELETE' && m.path === '/transactions/api/fx/5/'), `${context}: FX deletion through its own endpoint`)
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  // --- Slow detail reply loads before enabling confirm --------------------
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].find(b => b.getAttribute('aria-label').includes('UST 2.375% 31')); btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]') !== null`)
  probe = await evalProbe(run, `(() => ({
    loading: document.querySelector('.v-overlay--active[role="dialog"]').innerText.includes('Loading transaction details'),
    confirmDisabled: document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').disabled,
  }))()`, context)
  assert.equal(probe.loading, true, `${context}: detail loading state`)
  assert.equal(probe.confirmDisabled, true, `${context}: confirmation disabled while details load`)
  fixtureServer.releaseRead('/transactions/api/7/')
  await run(['wait', '600'])
  probe = await dialogText()
  assert.match(probe ?? '', /498\.25 EUR/, `${context}: loaded detail amounts carry their own serializer currency`)
  probe = await evalProbe(run, `document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').disabled`, context)
  assert.equal(probe, false, `${context}: confirmation enabled after details load`)
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  // --- Detail failure disables deletion ------------------------------------
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')].find(b => b.getAttribute('aria-label').includes('TSMC ADR')); btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]')?.innerText.includes('Could not load')`)
  probe = await evalProbe(run, `(() => ({
    text: document.querySelector('.v-overlay--active[role="dialog"]').innerText.replace(/\\s+/g, ' '),
    confirmDisabled: document.querySelector('.v-overlay--active [data-testid="confirm-confirm"]').disabled,
    cancelEnabled: !document.querySelector('.v-overlay--active [data-testid="confirm-cancel"]').disabled,
}))()`, context)
  assert.match(probe.text, /Could not load the transaction details/, `${context}: detail failure surfaced`)
  assert.equal(probe.confirmDisabled, true, `${context}: deletion disabled after detail failure`)
  assert.equal(probe.cancelEnabled, true, `${context}: cancel remains available`)
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  // --- Rejected regular save preserves fields; retry succeeds -------------
  await run(['eval', `document.querySelector('[data-action="add-transaction"]').click()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"] input[type="date"]') !== null`)
  await run(['eval', `(() => {
    const dialog = document.querySelector('.v-overlay--active[role="dialog"]')
    const setInput = (label, value) => {
      const input = [...dialog.querySelectorAll('label')].find(el => el.textContent.trim() === label)?.closest('.v-input')?.querySelector('input')
      input.value = value
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
    setInput('Date', '2026-09-09')
    setInput('Quantity', '12')
    setInput('Price', '150.25')
    setInput('Cash flow', '-1803')
    return true
  })()`])
  await run(['eval', `(() => { const save = [...document.querySelectorAll('.v-overlay--active button')].find(b => b.textContent.trim() === 'Save'); save.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]')?.innerText.includes('Synthetic quantity rejection')`)
  probe = await evalProbe(run, `(() => {
    const dialog = document.querySelector('.v-overlay--active[role="dialog"]')
    const value = (label) => [...dialog.querySelectorAll('label')].find(el => el.textContent.trim() === label)?.closest('.v-input')?.querySelector('input')?.value
    return {
      text: dialog.innerText.replace(/\\s+/g, ' '),
      quantity: value('Quantity'),
      price: value('Price'),
      cash: value('Cash flow'),
      sections: [...dialog.querySelectorAll('h3')].map(el => el.textContent.trim()),
    }
  })()`, context)
  assert.match(probe.text, /Synthetic quantity rejection/, `${context}: inline field error from the server`)
  assert.match(probe.text, /Synthetic server rejection/, `${context}: general error from the server`)
  assert.equal(probe.quantity, '12', `${context}: entered quantity preserved`)
  assert.equal(probe.price, '150.25', `${context}: entered price preserved`)
  assert.equal(probe.cash, '-1803', `${context}: entered cash flow preserved`)
  assert.deepEqual(probe.sections, ['Transaction details', 'Amounts'], `${context}: visible form section labels`)
  await run(['eval', `(() => { const dialog = document.querySelector('.v-overlay--active[role="dialog"]'); const input = [...dialog.querySelectorAll('label')].find(el => el.textContent.trim() === 'Quantity')?.closest('.v-input')?.querySelector('input'); input.value = '13'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); return true })()`])
  await run(['eval', `(() => { const save = [...document.querySelectorAll('.v-overlay--active button')].find(b => b.textContent.trim() === 'Save'); save.click(); return true })()`])
  await run(['wait', '700'])
  const addMutations = fixtureServer.d4.mutations.filter((m) => m.method === 'POST' && m.path === '/transactions/api/')
  assert.equal(addMutations.length, 2, `${context}: exactly two save attempts (rejection then correction)`)
  const retry = addMutations.at(-1)
  assert.equal(retry.body.quantity, '13', `${context}: corrected payload sent verbatim`)
  assert.equal(retry.body.price, '150.25', `${context}: preserved fields resent verbatim`)

  await log({ context, status: 'd4 transactions flow passed' })
  console.log('PASS d4 transactions flow')
}

/** Quick per-viewport checks: controls really visible/hittable, no page
    overflow, caption present. */
export async function assertD4ViewportChecks({ appOrigin, context, initScript, log, session, viewport, route }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  await run(['open', `${appOrigin}${route}`])
  await waitFor(run, `document.querySelector('.positions-table tbody tr, .workspace-table-toolbar') !== null`)
  await run(['wait', '250'])
  const probe = await evalProbe(run, `(() => {
    const overflowX = document.documentElement.scrollWidth - document.documentElement.clientWidth
    const toolbar = document.querySelector('.positions-workspace .workspace-table-toolbar, .workspace-ui .workspace-table-toolbar')
    const measure = (el) => {
      if (!el) return { missing: true }
      const r = el.getBoundingClientRect()
      const hit = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + Math.min(r.height / 2, 24)))
      return { w: Math.round(r.width), h: Math.round(r.height), hit: !!hit && el.contains(hit) }
    }
    const isPositions = location.pathname.includes('positions')
    return {
      overflowX,
      caption: isPositions ? !!document.querySelector('.positions-table table caption') : true,
      year: { skip: !isPositions, ...measure(toolbar?.querySelector('.positions-year-select')) },
      search: measure(toolbar?.querySelector('.workspace-table-toolbar__search')),
      view: { skip: !isPositions, ...measure(toolbar?.querySelector('.positions-view-select')) },
      columns: { skip: !isPositions, ...measure(toolbar?.querySelector('button[aria-label="Show or hide columns"]')) },
      rows: measure(toolbar?.querySelector('.workspace-table-toolbar__rows')),
      addTransaction: { skip: isPositions, ...measure(document.querySelector('[data-action="add-transaction"]')) },
    }
  })()`, context)
  assert.ok(probe.overflowX <= 0, `${context}: no page-level horizontal overflow (${probe.overflowX}px)`)
  if (route.includes('positions')) assert.equal(probe.caption, true, `${context}: caption present`)
  for (const [name, control] of Object.entries({ year: probe.year, search: probe.search, view: probe.view, columns: probe.columns, rows: probe.rows, addTransaction: probe.addTransaction })) {
    if (control.skip) continue
    assert.ok(!control.missing, `${context}: ${name} present`)
    assert.ok(control.w > 0 && control.h >= 24, `${context}: ${name} has a usable target`)
    assert.ok(control.hit, `${context}: ${name} is really visible (hit-test)`)
  }
  await log({ context, viewport: viewport.name, probe, status: 'viewport checks passed' })
  console.log(`PASS ${viewport.name} ${route} d4 viewport checks`)
}

/** The seven named captures for the design evidence. */
export async function captureD4Screenshots({ appOrigin, context, initScript, log, session }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const shotsDir = resolve(process.cwd(), '../docs/design/assets/frontend-workspace')
  const shot = (name) => run(['screenshot', resolve(shotsDir, name)])

  const openPositions = async () => {
    await run(['open', `${appOrigin}/open-positions`])
    await waitFor(run, `document.querySelectorAll('.positions-table tbody tr').length > 1`)
    await run(['wait', '300'])
  }
  const closedPositions = async () => {
    await run(['open', `${appOrigin}/closed-positions`])
    await waitFor(run, `document.querySelectorAll('.positions-table tbody tr').length > 1`)
    await run(['wait', '300'])
  }
  const setViewport = (w, h) => run(['set', 'viewport', String(w), String(h)])
  // localStorage is only accessible on an opened origin (about:blank denies
  // it), so always open the app before resetting view preferences.
  const resetPreferences = async () => {
    await run(['open', `${appOrigin}/open-positions`])
    await run(['wait', '250'])
    await run(['eval', `(() => { localStorage.removeItem('positionsTableView.v1.u1.open-positions'); localStorage.removeItem('positionsTableView.v1.u1.closed-positions'); return true })()`])
    await run(['open', `${appOrigin}/open-positions`])
    await run(['wait', '250'])
  }

  await setViewport(1440, 1000)
  await resetPreferences()
  await openPositions()
  await shot('d4-open-overview-desktop.png')

  await pickViewItem(run, 'Full ledger')
  await run(['wait', '300'])
  await shot('d4-open-ledger-desktop.png')

  await setViewport(390, 844)
  await resetPreferences()
  await openPositions()
  await shot('d4-open-overview-mobile.png')

  await closedPositions()
  await shot('d4-closed-overview-mobile.png')

  // Columns chooser open on mobile.
  await run(['eval', `document.querySelector('.positions-workspace button[aria-label="Show or hide columns"]').click()`])
  await waitFor(run, `document.querySelector('.v-overlay--active .positions-columns-menu') !== null`)
  await run(['wait', '300'])
  await shot('d4-columns-mobile.png')
  await run(['press', 'Escape'])
  await run(['wait', '200'])

  await setViewport(1440, 1000)
  await resetPreferences()
  await closedPositions()
  await pickViewItem(run, 'Entry & exit')
  await run(['wait', '300'])
  await shot('d4-closed-comparison-desktop.png')

  await run(['open', `${appOrigin}/transactions`])
  await waitFor(run, `document.querySelectorAll('tbody button[aria-label^="Delete"]').length >= 2`)
  await run(['eval', `(() => { const btn = [...document.querySelectorAll('tbody button[aria-label^="Delete"]')][0]; btn.focus(); btn.click(); return true })()`])
  await waitFor(run, `document.querySelector('.v-overlay--active[role="dialog"]') !== null`)
  await run(['wait', '300'])
  await shot('d4-transaction-confirmation.png')
  await run(['press', 'Escape'])
  await run(['wait', '200'])
  await log({ context, status: 'd4 screenshots captured' })
  console.log('PASS d4 screenshots')
}
