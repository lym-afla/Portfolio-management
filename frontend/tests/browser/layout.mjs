import assert from 'node:assert/strict'

import { runAgentBrowser } from './protocol.mjs'

export async function assertLayoutGeometry({
  context,
  initScript,
  log,
  session,
}) {
  await runAgentBrowser({
    args: ['snapshot', '-i'],
    context: `${context} interactive snapshot`,
    initScript,
    log,
    session,
  })

  const { result } = await runAgentBrowser({
    args: [
      'eval',
      `(() => {
        const bar = document.querySelector('.v-app-bar')
        const content = document.querySelector('[data-testid="route-content"]')
        if (!bar || !content) return { missing: { bar: !bar, content: !content } }
        const barRect = bar.getBoundingClientRect()
        const contentRect = content.getBoundingClientRect()
        const intrinsic = bar.querySelector('[data-testid="app-bar-content"]')?.getBoundingClientRect()
        const controlOverflow = [...bar.querySelectorAll('h2, .account-selection, .v-btn, .workspace-context .v-input, .workspace-context__preferences')]
          .filter((element) => element.getBoundingClientRect().width > 0)
          .filter((element) => {
            const rect = element.getBoundingClientRect()
            return rect.left < barRect.left - 1 || rect.right > barRect.right + 1
          })
          .map((element) => element.className)
        const layoutTop = parseFloat(getComputedStyle(document.querySelector('.v-main')).paddingTop)
        return {
          headerBottom: barRect.bottom,
          headerHeight: barRect.height,
          contentTop: contentRect.top,
          intrinsicBottom: intrinsic?.bottom ?? null,
          intrinsicHeight: intrinsic?.height ?? null,
          accountName: bar.querySelector('.v-select__selection-text')?.textContent?.trim() ?? null,
          accountTop: bar.querySelector('.account-selection')?.getBoundingClientRect().top ?? null,
          settingsTop: bar.querySelector('.account-selection + div')?.getBoundingClientRect().top ?? null,
          controlOverflow,
          layoutTop,
          scrollY,
        }
      })()`,
    ],
    context: `${context} layout geometry`,
    initScript,
    log,
    session,
  })

  assert.ok(
    !result.missing,
    `${context}: missing rendered layout node: ${JSON.stringify(result)}`
  )
  assert.equal(result.scrollY, 0, `${context}: page must start at scroll zero`)
  assert.ok(
    result.layoutTop > 0,
    `${context}: Vuetify must register a positive top offset: ${JSON.stringify(result)}`
  )
  assert.deepEqual(
    result.controlOverflow,
    [],
    `${context}: header control extends past the app bar`
  )
  assert.ok(
    result.contentTop >= result.headerBottom - 1,
    `${context}: header covers route content: ${JSON.stringify(result)}`
  )
  if (result.intrinsicBottom !== null) {
    assert.ok(
      result.intrinsicBottom <= result.headerBottom + 1,
      `${context}: header clips its intrinsic content: ${JSON.stringify(result)}`
    )
    assert.ok(
      result.headerHeight - result.intrinsicHeight <= 2,
      `${context}: registered header height exceeds its content: ${JSON.stringify(result)}`
    )
  }
  return result
}

export async function assertFocusedLayoutFlow({
  context,
  initScript,
  log,
  session,
  viewport,
}) {
  let snapshot = await runAgentBrowser({
    args: ['snapshot', '-i'],
    context: `${context} navigation snapshot`,
    initScript,
    log,
    session,
  })
  const preferencesRef = Object.entries(snapshot.refs).find(
    ([, item]) => item.role === 'button' && item.name === 'Display preferences'
  )?.[0]
  assert.ok(preferencesRef, 'Performance preferences must remain reachable')
  await runAgentBrowser({
    args: ['click', `@${preferencesRef}`],
    context,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['wait', '250'],
    context,
    initScript,
    log,
    session,
  })
  const settings = await runAgentBrowser({
    args: [
      'eval',
      `({ date: document.querySelector('.v-dialog input[type="date"]')?.value, digits: document.querySelector('.v-dialog input[type="number"]')?.value, currency: document.querySelector('.v-dialog .v-select__selection-text')?.textContent })`,
    ],
    context,
    initScript,
    log,
    session,
  })
  assert.equal(settings.result.date, '2026-09-08')
  assert.equal(settings.result.digits, '2')
  assert.match(settings.result.currency, /US Dollar/)
  snapshot = await runAgentBrowser({
    args: ['snapshot', '-i'],
    context,
    initScript,
    log,
    session,
  })
  const closeRef = Object.entries(snapshot.refs).find(
    ([, item]) => item.role === 'button' && item.name.toLowerCase() === 'close'
  )?.[0]
  assert.ok(closeRef)
  await runAgentBrowser({
    args: ['click', `@${closeRef}`],
    context,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['wait', '250'],
    context,
    initScript,
    log,
    session,
  })
  snapshot = await runAgentBrowser({
    args: ['snapshot', '-i'],
    context,
    initScript,
    log,
    session,
  })
  const openRef = Object.entries(snapshot.refs).find(
    ([, item]) => item.role === 'button' && item.name === 'Open navigation'
  )?.[0]
  if (openRef) {
    await runAgentBrowser({
      args: ['click', `@${openRef}`],
      context,
      initScript,
      log,
      session,
    })
    await runAgentBrowser({
      args: ['press', 'Escape'],
      context,
      initScript,
      log,
      session,
    })
    await runAgentBrowser({
      args: ['wait', '250'],
      context,
      initScript,
      log,
      session,
    })
    const focus = await runAgentBrowser({
      args: ['eval', `document.activeElement?.getAttribute('aria-label')`],
      context,
      initScript,
      log,
      session,
    })
    assert.equal(
      focus.result,
      'Open navigation',
      'Escape must restore focus to navigation trigger'
    )
    await runAgentBrowser({
      args: ['click', '[aria-label="Open navigation"]'],
      context,
      initScript,
      log,
      session,
    })
    snapshot = await runAgentBrowser({
      args: ['snapshot', '-i'],
      context,
      initScript,
      log,
      session,
    })
  }
  const dashboardRef = Object.entries(snapshot.refs).find(
    ([, item]) => item.role === 'link' && item.name === 'Overview'
  )?.[0]
  assert.ok(dashboardRef, `${context}: Dashboard navigation link missing`)
  await runAgentBrowser({
    args: ['click', `@${dashboardRef}`],
    context: `${context} SPA transition to dashboard`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['wait', '250'],
    context: `${context} transition settle`,
    initScript,
    log,
    session,
  })
  const path = await runAgentBrowser({
    args: ['eval', 'location.pathname'],
    context: `${context} transition path`,
    initScript,
    log,
    session,
  })
  assert.equal(
    path.result,
    '/dashboard',
    `${context}: navigation must use the mounted route`
  )

  const base = await assertLayoutGeometry({
    context: `${context} after SPA transition`,
    initScript,
    log,
    session,
  })
  assert.match(base.accountName ?? '', /Long synthetic investment account name/)
  if (viewport.name === 'mobile') {
    assert.ok(
      base.settingsTop > base.accountTop + 1,
      `${context}: account/settings row did not wrap at narrow width: ${JSON.stringify(base)}`
    )
  }

  await runAgentBrowser({
    args: [
      'eval',
      `(() => {
      // The shell releases its duplicate heading when the route owns one
      // (D1 heading ownership); either element is the single page title.
      const title = document.querySelector('[data-testid="legacy-page-heading"], [data-testid="workspace-page-heading"]')
      if (!title) throw new Error('Scrollable page title missing')
      title.textContent = 'Consolidated portfolio for international and restricted investments across multiple accounts and currencies, with a longer descriptive title for this view'
    })()`,
    ],
    context: `${context} long title`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({
    args: ['wait', '100'],
    context: `${context} reflow settle`,
    initScript,
    log,
    session,
  })
  const wrapped = await assertLayoutGeometry({
    context: `${context} wrapped title`,
    initScript,
    log,
    session,
  })
  assert.ok(
    Math.abs(wrapped.headerHeight - base.headerHeight) <= 1,
    `${context}: long scrollable heading must not enlarge the fixed context header: ${JSON.stringify({ base, wrapped })}`
  )
  assert.ok(
    wrapped.headerBottom < viewport.height * 0.75,
    `${context}: wrapped header leaves too little of the viewport for route content: ${JSON.stringify(wrapped)}`
  )
  const heading = await runAgentBrowser({
    args: [
      'eval',
      `(() => { const h = document.querySelector('[data-testid="legacy-page-heading"], [data-testid="workspace-page-heading"]'); const r = h.getBoundingClientRect(); return { inMain: !!h.closest('.v-main'), count: document.querySelectorAll('h1').length, bottom: r.bottom, top: r.top, right: r.right, contentRight: h.parentElement.getBoundingClientRect().right } })()`,
    ],
    context,
    initScript,
    log,
    session,
  })
  assert.equal(heading.result.inMain, true)
  assert.equal(heading.result.count, 1)
  assert.ok(heading.result.top >= wrapped.headerBottom - 1)
  assert.ok(heading.result.right <= heading.result.contentRight + 1)
  const consoleData = await runAgentBrowser({
    args: ['console'],
    context: `${context} console warnings`,
    initScript,
    log,
    session,
  })
  assert.doesNotMatch(JSON.stringify(consoleData), /ResizeObserver loop/i)
  return { base, wrapped }
}

/** Positions toolbar: every control must be really visible (hit-test, not
    clipped by the fixed-height toolbar box) and the Columns menu usable. */
export async function assertPositionsToolbarFlow({ appOrigin, context, initScript, log, session, viewport }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  await run(['open', `${appOrigin}/open-positions`])
  await run(['wait', '--fn', "document.querySelectorAll('.v-data-table tbody tr').length > 1"])
  await run(['eval', "document.querySelector('.v-data-table .v-toolbar')?.scrollIntoView({ block: 'center' })"])
  await run(['wait', '150'])

  const controls = await runAgentBrowser({
    args: [
      'eval',
      `(() => {
        const toolbar = document.querySelector('.v-data-table .v-toolbar')
        const box = toolbar.querySelector('.v-toolbar__content').getBoundingClientRect()
        const year = toolbar.querySelector('.v-select:not(.rows-per-page-select)')
        const search = toolbar.querySelector('.v-text-field')
        const columns = toolbar.querySelector('button[aria-label="Show or hide columns"]')
        const rows = toolbar.querySelector('.rows-per-page-select')
        const measure = (name, el) => {
          if (!el) return { name, missing: true }
          const r = el.getBoundingClientRect()
          const cx = Math.round(r.left + r.width / 2), cy = Math.round(r.top + Math.min(r.height / 2, 24))
          const hit = document.elementFromPoint(cx, cy)
          return {
            name,
            width: Math.round(r.width),
            height: Math.round(r.height),
            withinViewport: r.left >= -1 && r.right <= window.innerWidth + 1,
            insideToolbarBox: r.top >= box.top - 1 && r.bottom <= box.bottom + 1,
            hitIsControlOrChild: !!hit && !!el.contains(hit),
            hitTag: hit ? hit.tagName : null,
          }
        }
        return {
          toolbarBox: { top: Math.round(box.top), height: Math.round(box.height) },
          controls: [
            measure('year', year),
            measure('search', search),
            measure('columns', columns),
            measure('rows-per-page', rows),
          ],
        }
      })()`,
    ],
    context: `${context} positions toolbar probe`,
    initScript,
    log,
    session,
  })
  const probe = controls.result
  assert.ok(probe.toolbarBox.height > 0, `${context}: toolbar box missing`)
  for (const control of probe.controls) {
    assert.ok(!control.missing, `${context}: positions toolbar control missing: ${JSON.stringify(control)}`)
    assert.ok(control.width > 0 && control.height >= 24, `${context}: ${control.name} has no usable target: ${JSON.stringify(control)}`)
    assert.ok(control.withinViewport, `${context}: ${control.name} extends past the viewport: ${JSON.stringify(control)}`)
    assert.ok(control.insideToolbarBox, `${context}: ${control.name} is clipped outside the toolbar box: ${JSON.stringify({ ...control, toolbarBox: probe.toolbarBox })}`)
    assert.ok(control.hitIsControlOrChild, `${context}: ${control.name} is not really visible — center point is covered by ${control.hitTag}: ${JSON.stringify(control)}`)
  }

  const menu = await run(['eval', `(() => { const btn = document.querySelector('.v-data-table .v-toolbar button[aria-label="Show or hide columns"]'); btn.click(); return true })()`])
  assert.equal(menu.result, true)
  await run(['wait', '--fn', "document.querySelector('.v-overlay--active .v-list-item') !== null"])
  await run(['press', 'Escape'])
  await run(['wait', '--fn', "document.querySelector('.v-overlay--active .v-list-item') === null"])
  await log({ context, viewport: viewport.name, probe, status: 'passed' })
  console.log(`PASS ${viewport.name} positions toolbar usable`)
  return probe
}
