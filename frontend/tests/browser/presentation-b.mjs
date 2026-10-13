import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

import { runAgentBrowser } from './protocol.mjs'

const evalProbe = async (run, expression) =>
  (await run(['eval', expression])).result
const waitFor = (run, fn, timeout = 15000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

// Presentation phase B (release-validation Tasks 4-5): compact expanding
// navigation rail, header geometry (no duplicated context text, no unused
// toolbar space, equal control heights, unclipped labels), shared table
// rules (visible row separators, black header-bottom rule, clear totals
// rules), modernized security links, italic allocation share cells and the
// responsive transaction actions. Overflow is never hidden to fake a pass:
// probes hit-test and measure real geometry.
export async function assertPresentationBFlow({
  appOrigin,
  context,
  initScript,
  log,
  session,
  viewport,
  screenshotsDir,
}) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const shot = async (name) => {
    await mkdir(screenshotsDir, { recursive: true })
    const path = resolve(screenshotsDir, `presentation-b-${name}.png`)
    await run(['screenshot', path])
    return path
  }
  const isDesktop = viewport.name === 'desktop'
  const INK = 'rgb(23, 43, 77)'

  // ---------- /dashboard: shell geometry, rail, over-time table ----------
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.body.innerText.includes('Total NAV') || document.body.innerText.includes('Overview')`)
  await run(['wait', '400'])

  const shell = await evalProbe(run, `(() => {
    const bar = document.querySelector('.v-app-bar')
    const strip = document.querySelector('.workspace-context')
    const rail = document.querySelector('.v-navigation-drawer')
    const accountField = document.querySelector('.workspace-context-account .v-field')
    const settingsFields = [...document.querySelectorAll('.workspace-context-settings .v-field')]
    const arrows = [...document.querySelectorAll('.arrow-btn')]
    const accountLabel = document.querySelector('.workspace-context-account .v-field-label')
    const labelRect = accountLabel ? accountLabel.getBoundingClientRect() : null
    const labelHit = labelRect ? (() => {
      const cx = Math.round(labelRect.left + labelRect.width / 2)
      const cy = Math.round(labelRect.top + labelRect.height / 2)
      const hit = document.elementFromPoint(cx, cy)
      return !!hit && (!!accountLabel.contains(hit) || !!hit.closest('.v-field'))
    })() : null
    const divider = bar ? bar.querySelectorAll('.v-divider').length : null
    const emptyTitleRow = bar ? [...bar.querySelectorAll('.app-bar-title')].filter(el => el.getBoundingClientRect().height > 0).length : null
    const overTime = document.querySelector('.v-table .v-table__wrapper > table')
    let overTimeRules = null
    if (overTime && overTime.querySelector('thead')) {
      const rows = overTime.querySelectorAll('thead tr')
      const lastTh = rows.length ? rows[rows.length - 1].querySelector('th') : null
      const td = overTime.querySelector('tbody tr td')
      overTimeRules = {
        headerRule: lastTh ? getComputedStyle(lastTh).borderBottom : null,
        headerShadow: lastTh ? getComputedStyle(lastTh).boxShadow : null,
        rowRule: td ? getComputedStyle(td).borderBottom : null,
      }
    }
    return {
      hasBar: !!bar,
      stripText: strip ? strip.innerText.replace(/\\s+/g, ' ') : null,
      duplicatesSummary: strip ? /Valuation date:|Reporting currency:/.test(strip.innerText) : null,
      accountFieldH: accountField ? Math.round(accountField.getBoundingClientRect().height) : null,
      settingsH: settingsFields.map(f => Math.round(f.getBoundingClientRect().height)),
      arrowH: arrows.map(a => Math.round(a.getBoundingClientRect().height)),
      labelTop: labelRect ? Math.round(labelRect.top) : null,
      labelBottom: labelRect ? Math.round(labelRect.bottom) : null,
      fieldTop: accountField ? Math.round(accountField.getBoundingClientRect().top) : null,
      labelHit,
      barDividers: divider,
      visibleEmptyTitleRows: emptyTitleRow,
      railWidth: rail ? Math.round(rail.getBoundingClientRect().width) : null,
      railCollapsed: rail ? rail.classList.contains('v-navigation-drawer--rail') : null,
      railItemHeights: rail ? [...rail.querySelectorAll('.v-list-item')].map(i => Math.round(i.getBoundingClientRect().height)) : [],
      activeItem: rail ? rail.querySelector('[aria-current="page"]')?.textContent?.trim() ?? null : null,
      overTimeRules,
      rawObject: document.body.innerText.includes('[object Object]'),
    }
  })()`)

  assert.equal(shell.rawObject, false, `${context}: no raw [object Object] anywhere`)
  assert.equal(shell.duplicatesSummary, false, `${context}: the context strip must not duplicate the committed summary text: ${JSON.stringify(shell.stripText)}`)
  assert.equal(shell.barDividers, 0, `${context}: the unwanted header divider must be gone`)
  if (isDesktop) {
    assert.equal(shell.visibleEmptyTitleRows, 0, `${context}: the empty header line must be gone on non-summary pages`)
  }
  assert.equal(shell.accountFieldH, 56, `${context}: account control height must equal its siblings`)
  for (const h of shell.settingsH) assert.ok(Math.abs(h - 56) <= 1, `${context}: date/currency controls must be 56px tall, got ${JSON.stringify(shell.settingsH)}`)
  if (isDesktop) {
    for (const h of shell.arrowH) assert.ok(Math.abs(h - 56) <= 1, `${context}: arrow buttons must match the control row height`)
  } else {
    // Below 600px the arrows collapse away (the select spans the row) — the
    // deliberate narrow-layout behavior, so their measured height is 0.
    for (const h of shell.arrowH) assert.equal(h, 0, `${context}: arrows must be hidden, not mismatched, on narrow layouts`)
  }
  assert.ok(shell.labelTop !== null, `${context}: account floating label missing`)
  assert.ok(
    shell.labelHit,
    `${context}: the floated account label is not really visible (covered or clipped): ${JSON.stringify({ labelTop: shell.labelTop, fieldTop: shell.fieldTop })}`
  )
  assert.ok(
    shell.labelTop >= (shell.fieldTop ?? 0) - 24,
    `${context}: floated label escaped its field: ${JSON.stringify(shell)}`
  )
  if (overTimeRulesPresent(shell.overTimeRules)) {
    assert.match(
      ruleColor(shell.overTimeRules.headerRule) ?? shadowColor(shell.overTimeRules.headerShadow),
      new RegExp(INK.replace('(', '\\(').replace(')', '\\)')),
      `${context}: the over-time header must carry the ink bottom rule: ${JSON.stringify(shell.overTimeRules)}`
    )
    assert.match(
      shell.overTimeRules.rowRule,
      /1px solid rgb\(226, 230, 235\)/,
      `${context}: over-time row separators must be fully visible: ${JSON.stringify(shell.overTimeRules)}`
    )
  }

  if (isDesktop) {
    // ---- Compact rail: collapsed by default; expands on pointer hover and
    // ---- keyboard focus; collapses after BOTH leave.
    assert.equal(shell.railCollapsed, true, `${context}: desktop navigation must be a compact rail`)
    assert.ok(shell.railWidth >= 44 && shell.railWidth <= 100, `${context}: collapsed rail width must be compact, got ${shell.railWidth}`)
    for (const h of shell.railItemHeights) assert.ok(h >= 44, `${context}: rail items keep usable hit areas (got ${shell.railItemHeights})`)
    assert.equal(shell.activeItem, 'Overview', `${context}: the active route label must stay on its item`)

    const railCenter = await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      const r = rail.getBoundingClientRect()
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + Math.min(r.height / 2, 400)) }
    })()`)
    await run(['mouse', 'move', String(Math.max(1, railCenter.x - 30)), String(railCenter.y)])
    await run(['mouse', 'move', String(railCenter.x), String(railCenter.y)])
    await run(['wait', '350'])
    const hovered = await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      const subheaders = [...rail.querySelectorAll('.v-list-subheader')]
      return {
        hovering: rail.classList.contains('v-navigation-drawer--is-hovering'),
        width: Math.round(rail.getBoundingClientRect().width),
        subheaders: subheaders.length,
        subheaderHeights: subheaders.map(s => Math.round(s.getBoundingClientRect().height)),
        mainLeft: Math.round(document.querySelector('main').getBoundingClientRect().left),
      }
    })()`)
    assert.equal(hovered.hovering, true, `${context}: pointer hover must expand the rail`)
    assert.ok(hovered.width > 180, `${context}: expanded rail shows the labels (width ${hovered.width})`)
    assert.ok(hovered.subheaders > 0, `${context}: expanded rail shows the section grouping`)
    for (const h of hovered.subheaderHeights) assert.ok(h >= 24, `${context}: expanded section headers show their labels`)
    assert.equal(hovered.mainLeft, 0, `${context}: expansion must overlay, not push, the page`)
    await shot('rail-expanded-hover')

    // Plain pointer leave collapses it again.
    await run(['mouse', 'move', String(railCenter.x + 400), String(railCenter.y)])
    await run(['wait', '350'])
    const pointerCollapsed = await evalProbe(run, `(() => ({
      hovering: document.querySelector('.v-navigation-drawer').classList.contains('v-navigation-drawer--is-hovering'),
    }))()`)
    assert.equal(pointerCollapsed.hovering, false, `${context}: pointer leave collapses the expanded rail`)

    // Pointer leaves but focus stays inside: it must stay expanded. Then
    // focus leaves too, and only the combination collapses it.
    await run(['mouse', 'move', String(railCenter.x - 30), String(railCenter.y)])
    await run(['mouse', 'move', String(railCenter.x), String(railCenter.y)])
    await run(['wait', '350'])
    const focusProbe = await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      const item = rail.querySelector('.v-list-item')
      item.focus()
      return { focused: document.activeElement === item }
    })()`)
    assert.equal(focusProbe.focused, true, `${context}: rail items must be keyboard-focusable`)
    await run(['wait', '200'])
    // Pointer leaves while the keyboard focus stays inside.
    await run(['mouse', 'move', String(railCenter.x + 400), String(railCenter.y)])
    await run(['wait', '350'])
    const focusExpanded = await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      return { hovering: rail.classList.contains('v-navigation-drawer--is-hovering'), width: Math.round(rail.getBoundingClientRect().width) }
    })()`)
    assert.equal(focusExpanded.hovering, true, `${context}: pointer leave must NOT collapse while keyboard focus stays inside: ${JSON.stringify(focusExpanded)}`)
    // Now focus leaves as well: both gone, the rail collapses.
    await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      const item = rail.querySelector('.v-list-item')
      item.blur()
      rail.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      return true
    })()`)
    await run(['wait', '350'])
    const collapsed = await evalProbe(run, `(() => {
      const rail = document.querySelector('.v-navigation-drawer')
      const subheaders = [...rail.querySelectorAll('.v-list-subheader')]
      return {
        hovering: rail.classList.contains('v-navigation-drawer--is-hovering'),
        width: Math.round(rail.getBoundingClientRect().width),
        subheaders: subheaders.length,
        subheaderHeights: subheaders.map(s => Math.round(s.getBoundingClientRect().height)),
      }
    })()`)
    assert.equal(collapsed.hovering, false, `${context}: the rail must collapse after pointer and focus both leave`)
    assert.ok(collapsed.width <= 100, `${context}: collapsed rail restored, got ${collapsed.width}`)
    // The section headers stay in the tree (stable structure) but compress
    // so the compact rail shows icons only.
    assert.ok(collapsed.subheaders > 0, `${context}: section headers remain in the tree`)
    for (const h of collapsed.subheaderHeights) assert.ok(h <= 16, `${context}: collapsed section headers compress to separators: ${JSON.stringify(collapsed.subheaderHeights)}`)
    await shot('rail-collapsed-desktop')
  }

  // ---------- /profile: no unused toolbar region, no artificial scroll ----
  await run(['open', `${appOrigin}/profile`])
  await waitFor(run, `document.body.innerText.includes('User details')`)
  await run(['wait', '300'])
  const profile = await evalProbe(run, `(() => ({
    appBar: !!document.querySelector('.v-app-bar'),
    scrollHeight: document.documentElement.scrollHeight,
    innerHeight: window.innerHeight,
  }))()`)
  if (isDesktop) {
    assert.equal(profile.appBar, false, `${context}: the desktop Profile page must not render an empty app bar`)
  }
  assert.ok(
    profile.scrollHeight <= profile.innerHeight,
    `${context}: the short Profile page must not scroll artificially: ${JSON.stringify(profile)}`
  )
  if (isDesktop) {
    // A genuinely short viewport must not introduce artificial overflow.
    await run(['set', 'viewport', '1280', '430'])
    await run(['wait', '300'])
    const shortProfile = await evalProbe(run, `(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
    }))()`)
    assert.ok(
      shortProfile.scrollHeight <= shortProfile.innerHeight,
      `${context}: Profile overflows at a short viewport: ${JSON.stringify(shortProfile)}`
    )
    await run(['set', 'viewport', String(viewport.width), String(viewport.height)])
    await run(['wait', '250'])
  }

  // ---------- /open-positions: fixed-header rule, totals, sticky, scroll --
  await run(['open', `${appOrigin}/open-positions`])
  await waitFor(run, `document.querySelectorAll('.v-data-table tbody tr').length > 1`)
  await run(['wait', '300'])
  const positions = await evalProbe(run, `(() => {
    const table = document.querySelector('.v-data-table .v-table__wrapper > table')
    if (!table) return { missing: true }
    const theadRows = table.querySelectorAll('thead tr')
    const lastTh = theadRows.length ? theadRows[theadRows.length - 1].querySelector('th') : null
    const tds = table.querySelectorAll('tbody tr td')
    const tfootRows = table.querySelectorAll('tfoot tr')
    const tfootFirst = tfootRows.length ? tfootRows[0].querySelector('td, th') : null
    const tfootLast = tfootRows.length ? tfootRows[tfootRows.length - 1].querySelector('td, th') : null
    const pinned = table.querySelector('.col-pin-1')
    const region = document.querySelector('.v-table__wrapper')
    return {
      headerRule: lastTh ? getComputedStyle(lastTh).borderBottom : null,
      headerShadow: lastTh ? getComputedStyle(lastTh).boxShadow : null,
      rowRules: [...tds].slice(0, 3).map(td => getComputedStyle(td).borderBottom),
      tfootTopRule: tfootFirst ? getComputedStyle(tfootFirst).borderTop : null,
      tfootBottomRule: tfootLast ? getComputedStyle(tfootLast).borderBottom : null,
      pinnedSticky: pinned ? getComputedStyle(pinned).position : null,
      regionScrolls: region ? region.scrollWidth >= region.clientWidth : null,
      footerTexts: [...tfootRows].map(tr => tr.textContent.trim().slice(0, 20)),
    }
  })()`)
  assert.ok(!positions.missing, `${context}: positions table missing`)
  const positionsHeaderRule = ruleColor(positions.headerRule) ?? shadowColor(positions.headerShadow)
  assert.match(
    positionsHeaderRule ?? '',
    new RegExp(INK.replace('(', '\\(').replace(')', '\\)')),
    `${context}: positions header needs the ink bottom rule: ${JSON.stringify(positions.headerRule ?? positions.headerShadow)}`
  )
  for (const rule of positions.rowRules) {
    assert.match(rule, /1px solid rgb\(226, 230, 235\)/, `${context}: position row separators must be visible: ${rule}`)
  }
  assert.match(positions.tfootTopRule ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: totals rows need a clear top rule`)
  assert.match(positions.tfootBottomRule ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: totals rows need a clear bottom rule`)
  assert.equal(positions.pinnedSticky, 'sticky', `${context}: pinned columns must stay sticky`)
  await shot('positions-desktop-rules')

  // ---------- /summary: plain tables and TOTAL rules ----------------------
  await run(['open', `${appOrigin}/summary`])
  await waitFor(run, `document.querySelectorAll('.workspace-table').length > 0`)
  await run(['wait', '300'])
  const summary = await evalProbe(run, `(() => {
    const table = document.querySelector('.workspace-table')
    const theadRows = table ? table.querySelectorAll('thead tr') : []
    const lastTh = theadRows.length ? theadRows[theadRows.length - 1].querySelector('th') : null
    const td = table ? table.querySelector('tbody tr:not(.group-header):not(.total-row) td') : null
    const total = table ? table.querySelector('tr.total-row td, tr.total-row th') : null
    return {
      headerRule: lastTh ? getComputedStyle(lastTh).borderBottom : null,
      rowRule: td ? getComputedStyle(td).borderBottom : null,
      totalTop: total ? getComputedStyle(total).borderTop : null,
      totalBottom: total ? getComputedStyle(total).borderBottom : null,
    }
  })()`)
  assert.match(summary.headerRule ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: summary header ink rule missing`)
  assert.match(summary.rowRule ?? '', /1px solid rgb\(226, 230, 235\)/, `${context}: summary row separators invisible`)
  assert.match(summary.totalTop ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: summary TOTAL top rule missing`)
  assert.match(summary.totalBottom ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: summary TOTAL bottom rule missing`)

  // ---------- /transactions: actions, grouped header, links, transitions --
  await run(['open', `${appOrigin}/transactions`])
  await waitFor(run, `document.querySelectorAll('.workspace-actions-row [data-action]').length > 0`)
  // Wait out any in-flight fit measurement before probing the tiers.
  await waitFor(run, `document.querySelector('.workspace-actions-row--measuring') === null`)
  await run(['wait', '200'])
  const transactions = await evalProbe(run, `(() => {
    const table = document.querySelector('.v-data-table .v-table__wrapper > table')
    const theadRows = table ? table.querySelectorAll('thead tr') : []
    const lastTh = theadRows.length ? theadRows[theadRows.length - 1].querySelector('th') : null
    const link = document.querySelector('a.security-link')
    return {
      direct: [...document.querySelectorAll('.workspace-actions-row [data-action]')].map(e => e.getAttribute('data-action')),
      menuButton: !!document.querySelector('[data-testid="workspace-actions-more"]'),
      headerRows: theadRows.length,
      lastHeaderRule: lastTh ? getComputedStyle(lastTh).borderBottom : null,
      linkColor: link ? getComputedStyle(link).color : null,
      linkRestDecoration: link ? getComputedStyle(link).textDecorationLine : null,
    }
  })()`)
  if (isDesktop) {
    assert.deepEqual(
      transactions.direct,
      ['add-transaction', 'import-transactions', 'add-fx-transaction', 'transfer-asset', 'record-merger'],
      `${context}: wide rows show every candidate action directly, in order: ${JSON.stringify(transactions.direct)}`
    )
    assert.equal(transactions.menuButton, false, `${context}: nothing is hidden on a wide row, so the menu must be absent`)
  } else {
    assert.deepEqual(transactions.direct, ['add-transaction'], `${context}: narrow layouts keep only the primary action direct`)
    assert.equal(transactions.menuButton, true, `${context}: narrow layouts expose the overflow menu`)
  }
  assert.ok(transactions.headerRows >= 2, `${context}: grouped header must keep its two tiers`)
  assert.match(transactions.lastHeaderRule ?? '', new RegExp(INK.replace('(', '\\(').replace(')', '\\)')), `${context}: transactions header ink rule missing`)
  assert.match(transactions.linkColor ?? '', /rgb\(15, 76, 129\)/, `${context}: security links use the restrained primary color`)
  assert.equal(transactions.linkRestDecoration, 'none', `${context}: security links rest without an underline`)

  // Real pointer hover underlines the link (CDP mouse move, CSS :hover).
  if (transactions.linkColor) {
    const linkPoint = await evalProbe(run, `(() => {
      const link = document.querySelector('a.security-link')
      if (!link) return null
      link.scrollIntoView({ block: 'center' })
      const r = link.getBoundingClientRect()
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
    })()`)
    if (linkPoint) {
      await run(['mouse', 'move', String(Math.max(1, linkPoint.x - 8)), String(linkPoint.y)])
      await run(['mouse', 'move', String(linkPoint.x), String(linkPoint.y)])
      await run(['wait', '120'])
      const hoverUnderline = await evalProbe(run, `(() => ({
        decoration: getComputedStyle(document.querySelector('a.security-link')).textDecorationLine,
      }))()`)
      assert.equal(hoverUnderline.decoration, 'underline', `${context}: hovered security links must underline`)
    }
  }

  // Keyboard focus reaches the link and underlines it (:focus-visible).
  const focusedLink = await evalProbe(run, `(async () => {
    const link = document.querySelector('a.security-link')
    if (!link) return { missing: true }
    link.focus()
    await new Promise(r => setTimeout(r, 50))
    return {
      focused: document.activeElement === link,
      focusVisible: link.matches(':focus-visible'),
      decoration: getComputedStyle(link).textDecorationLine,
    }
  })()`)
  if (!focusedLink.missing) {
    assert.equal(focusedLink.focused, true, `${context}: security link must be keyboard-reachable`)
    if (focusedLink.focusVisible) {
      assert.equal(focusedLink.decoration, 'underline', `${context}: focused security links must underline`)
    }
  }

  if (isDesktop) {
    // Keyboard focus preservation (review round): the focused action's
    // identity is captured BEFORE the tiers change and restored to the same
    // action where it still exists, otherwise to the More actions activator.
    const focusProbe = await evalProbe(run, `(() => {
      const el = document.querySelector('.workspace-actions-row [data-action="transfer-asset"]')
      if (!el) return { missing: true }
      el.focus()
      return { focused: document.activeElement === el }
    })()`)
    assert.equal(focusProbe.missing, undefined, `${context}: transfer-asset renders directly on the wide row`)
    assert.equal(focusProbe.focused, true, `${context}: keyboard focus lands on the direct action`)

    // Desktop -> narrow: the focused action moves into the menu; focus must
    // follow to the activator, never drop to <body>.
    await run(['set', 'viewport', '390', '844'])
    await run(['wait', '600'])
    const narrow = await evalProbe(run, `(() => {
      const row = document.querySelector('.workspace-actions-row')
      const menu = document.querySelector('[data-testid="workspace-actions-more"]')
      return {
        direct: [...document.querySelectorAll('.workspace-actions-row [data-action]')].map(e => e.getAttribute('data-action')),
        menuButton: !!menu,
        overflow: row ? row.scrollWidth > row.clientWidth + 1 : null,
        focusTarget: document.activeElement?.getAttribute('data-testid') ?? document.activeElement?.tagName ?? null,
      }
    })()`)
    assert.deepEqual(narrow.direct, ['add-transaction'], `${context}: narrow layouts keep only the primary action direct: ${JSON.stringify(narrow.direct)}`)
    assert.equal(narrow.menuButton, true, `${context}: hidden actions move into the overflow menu`)
    assert.equal(narrow.overflow, false, `${context}: the actions row must not overflow its container`)
    assert.equal(narrow.focusTarget, 'workspace-actions-more', `${context}: desktop->narrow restores focus to the activator (got ${JSON.stringify(narrow.focusTarget)})`)
    // The menu lists exactly the hidden actions with their handlers.
    await evalProbe(run, `(() => { document.querySelector('[data-testid="workspace-actions-more"]').click(); return true })()`)
    await waitFor(run, `document.querySelector('.v-overlay--active .v-list-item[data-action]') !== null`)
    const menuItems = await evalProbe(run, `(() => ({
      items: [...document.querySelectorAll('.v-overlay--active .v-list-item[data-action]')].map(e => e.getAttribute('data-action')),
    }))()`)
    assert.deepEqual(
      menuItems.items,
      ['import-transactions', 'add-fx-transaction', 'transfer-asset', 'record-merger'],
      `${context}: the menu lists the hidden actions in order`
    )
    // Mobile table region still scrolls horizontally (no hidden overflow).
    const mobileTable = await evalProbe(run, `(() => {
      const region = document.querySelector('.v-data-table .v-table__wrapper')
      return { scrolls: region ? region.scrollWidth >= region.clientWidth : null }
    })()`)
    assert.equal(mobileTable.scrolls, true, `${context}: the transactions table must scroll horizontally at 390px`)
    // Narrow -> desktop WHILE THE MENU IS OPEN and a menu item focused: the
    // action becomes direct again and focus lands on that exact button.
    await evalProbe(run, `(() => {
      const item = document.querySelector('.v-overlay--active [data-action="import-transactions"]')
      item.focus()
      return document.activeElement === item
    })()`)
    await shot('transactions-390-menu')
    await run(['set', 'viewport', String(viewport.width), String(viewport.height)])
    await run(['wait', '600'])
    const restored = await evalProbe(run, `(() => ({
      direct: [...document.querySelectorAll('.workspace-actions-row [data-action]')].map(e => e.getAttribute('data-action')),
      menuButton: !!document.querySelector('[data-testid="workspace-actions-more"]'),
      focusAction: document.activeElement?.closest?.('[data-action]')?.getAttribute('data-action') ?? null,
      focusIsBody: document.activeElement === document.body,
      menuOpen: !!document.querySelector('.v-overlay--active .v-list-item[data-action]'),
      wrapped: document.querySelector('.workspace-actions-row')?.classList.contains('workspace-actions-row--wrapped') ?? null,
    }))()`)
    assert.equal(restored.menuButton, false, `${context}: restoring the width must reveal the actions again: ${JSON.stringify(restored)}`)
    assert.deepEqual(
      restored.direct,
      ['add-transaction', 'import-transactions', 'add-fx-transaction', 'transfer-asset', 'record-merger'],
      `${context}: all actions return direct after restore`
    )
    assert.equal(restored.focusAction, 'import-transactions', `${context}: narrow->desktop restores focus to the same action, now direct (got ${JSON.stringify(restored.focusAction)})`)
    assert.equal(restored.focusIsBody, false, `${context}: focus must never drop to <body> across the transition`)
    assert.equal(restored.menuOpen, false, `${context}: the menu closes once nothing is hidden`)
    assert.equal(restored.wrapped, false, `${context}: a fitting row is not wrapped`)
    await shot('transactions-desktop-actions')

    // Focus survives a resize whose fit keeps the action direct — no steal.
    await evalProbe(run, `(() => { document.querySelector('.workspace-actions-row [data-action="record-merger"]')?.focus(); return true })()`)
    await run(['set', 'viewport', String(viewport.width - 80), String(viewport.height)])
    await run(['wait', '500'])
    const keptFocus = await evalProbe(run, `(() => ({
      focusAction: document.activeElement?.closest?.('[data-action]')?.getAttribute('data-action') ?? null,
    }))()`)
    assert.equal(keptFocus.focusAction, 'record-merger', `${context}: focus stays on the same action across a refit that keeps it direct (got ${JSON.stringify(keptFocus.focusAction)})`)
    await run(['set', 'viewport', String(viewport.width), String(viewport.height)])
    await run(['wait', '400'])

    // Degenerate width: even the primary action and the activator cannot
    // share one line, so the row wraps instead of clipping anything.
    await run(['set', 'viewport', '260', '844'])
    await run(['wait', '700'])
    const degenerate = await evalProbe(run, `(() => {
      const row = document.querySelector('.workspace-actions-row')
      const within = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.left >= -1 && r.right <= innerWidth + 1 }
      return {
        wrapped: row?.classList.contains('workspace-actions-row--wrapped') ?? null,
        primaryVisible: within(document.querySelector('.workspace-actions-row [data-action="add-transaction"]')),
        activatorVisible: within(document.querySelector('[data-testid="workspace-actions-more"]')),
        overflow: row ? row.scrollWidth > row.clientWidth + 1 : null,
      }
    })()`)
    assert.equal(degenerate.wrapped, true, `${context}: the degenerate row must wrap instead of clipping (got ${JSON.stringify(degenerate)})`)
    assert.equal(degenerate.primaryVisible, true, `${context}: the primary action stays visible in the wrapped row`)
    assert.equal(degenerate.activatorVisible, true, `${context}: the activator stays visible in the wrapped row`)
    assert.equal(degenerate.overflow, false, `${context}: the wrapped row must not overflow horizontally`)
    await run(['set', 'viewport', String(viewport.width), String(viewport.height)])
    await run(['wait', '500'])
    const unwrapped = await evalProbe(run, `(() => ({
      wrapped: document.querySelector('.workspace-actions-row')?.classList.contains('workspace-actions-row--wrapped') ?? null,
    }))()`)
    assert.equal(unwrapped.wrapped, false, `${context}: the wrap fallback releases once the row fits again`)
    await shot('transactions-desktop-actions')
  } else {
    // Mobile pass: the explicit navigation toggle, trigger hit area and the
    // actions menu on the narrow layout.
    const trigger = await evalProbe(run, `(() => {
      const btn = document.querySelector('[aria-label="Open navigation"]')
      if (!btn) return { missing: true }
      const r = btn.getBoundingClientRect()
      const hit = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2))
      return { width: Math.round(r.width), height: Math.round(r.height), hit: !!hit && !!btn.contains(hit) }
    })()`)
    assert.ok(!trigger.missing, `${context}: the mobile navigation toggle must exist`)
    assert.ok(trigger.width >= 44 && trigger.height >= 44, `${context}: the navigation toggle keeps a 44px target: ${JSON.stringify(trigger)}`)
    assert.equal(trigger.hit, true, `${context}: the navigation toggle must be hittable`)
    await evalProbe(run, `(() => { document.querySelector('[aria-label="Open navigation"]').click(); return true })()`)
    await waitFor(run, `document.querySelector('.v-navigation-drawer.v-navigation-drawer--temporary.v-navigation-drawer--active') !== null`)
    const mobileNav = await evalProbe(run, `(() => {
      const drawer = document.querySelector('.v-navigation-drawer.v-navigation-drawer--temporary')
      return {
        sections: drawer ? drawer.querySelectorAll('.v-list-subheader').length : 0,
        activeLabel: drawer ? drawer.querySelector('[aria-current="page"]')?.textContent?.trim() ?? null : null,
      }
    })()`)
    assert.ok(mobileNav.sections > 0, `${context}: the mobile drawer shows the section grouping`)
    assert.equal(mobileNav.activeLabel, 'Transactions', `${context}: the mobile drawer keeps the active-route label`)
    await evalProbe(run, `(() => { document.querySelector('.v-navigation-drawer--temporary .v-list-item[aria-current="page"]').click(); return true })()`)
    await run(['wait', '400'])
    const closed = await evalProbe(run, `(() => ({
      open: !!document.querySelector('.v-navigation-drawer--temporary.v-navigation-drawer--active'),
      focus: document.activeElement?.getAttribute('aria-label') ?? null,
    }))()`)
    assert.equal(closed.open, false, `${context}: selecting a route closes the mobile drawer`)
    assert.equal(closed.focus, 'Open navigation', `${context}: focus returns to the toggle`)
    await shot('transactions-390-mobile')
  }

  await log({ context, viewport: viewport.name, shell, positions, summary, transactions, status: 'passed' })
  console.log(`PASS ${viewport.name} presentation-b`)
  return { shell, positions, summary, transactions }
}

function overTimeRulesPresent(rules) {
  return rules && (rules.headerRule || rules.headerShadow)
}
function ruleColor(rule) {
  const match = typeof rule === 'string' ? rule.match(/rgb\([^)]+\)/) : null
  return match ? match[0] : null
}
function shadowColor(shadow) {
  const match = typeof shadow === 'string' ? shadow.match(/rgb\([^)]+\)/) : null
  return match ? match[0] : null
}
