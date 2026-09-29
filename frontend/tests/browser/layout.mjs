import assert from 'node:assert/strict'

import { runAgentBrowser } from './protocol.mjs'

export async function assertLayoutGeometry({ context, initScript, log, session }) {
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
        const controlOverflow = [...bar.querySelectorAll('h2, .account-selection, .v-btn')]
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

  assert.ok(!result.missing, `${context}: missing rendered layout node: ${JSON.stringify(result)}`)
  assert.equal(result.scrollY, 0, `${context}: page must start at scroll zero`)
  assert.ok(result.layoutTop > 0, `${context}: Vuetify must register a positive top offset: ${JSON.stringify(result)}`)
  assert.deepEqual(result.controlOverflow, [], `${context}: header control extends past the app bar`)
  assert.ok(
    result.contentTop >= result.headerBottom - 1,
    `${context}: header covers route content: ${JSON.stringify(result)}`,
  )
  if (result.intrinsicBottom !== null) {
    assert.ok(
      result.intrinsicBottom <= result.headerBottom + 1,
      `${context}: header clips its intrinsic content: ${JSON.stringify(result)}`,
    )
    assert.ok(
      result.headerHeight - result.intrinsicHeight <= 2,
      `${context}: registered header height exceeds its content: ${JSON.stringify(result)}`,
    )
  }
  return result
}

export async function assertFocusedLayoutFlow({ context, initScript, log, session, viewport }) {
  const snapshot = await runAgentBrowser({
    args: ['snapshot', '-i'],
    context: `${context} navigation snapshot`,
    initScript,
    log,
    session,
  })
  const dashboardRef = Object.entries(snapshot.refs).find(([, item]) =>
    item.role === 'link' && item.name === 'Dashboard',
  )?.[0]
  assert.ok(dashboardRef, `${context}: Dashboard navigation link missing`)
  await runAgentBrowser({
    args: ['click', `@${dashboardRef}`],
    context: `${context} SPA transition to dashboard`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({ args: ['wait', '250'], context: `${context} transition settle`, initScript, log, session })
  const path = await runAgentBrowser({
    args: ['eval', 'location.pathname'],
    context: `${context} transition path`,
    initScript,
    log,
    session,
  })
  assert.equal(path.result, '/dashboard', `${context}: navigation must use the mounted route`)

  const base = await assertLayoutGeometry({ context: `${context} after SPA transition`, initScript, log, session })
  assert.match(base.accountName ?? '', /Long synthetic investment account name/)
  if (viewport.name === 'mobile') {
    assert.ok(
      base.settingsTop > base.accountTop + 1,
      `${context}: account/settings row did not wrap at narrow width: ${JSON.stringify(base)}`,
    )
  }

  await runAgentBrowser({
    args: ['eval', `(() => {
      const title = document.querySelector('.v-app-bar h2')
      if (!title) throw new Error('App-bar title missing')
      title.textContent = 'Consolidated portfolio for international and restricted investments across multiple accounts and currencies, with a longer descriptive title for this view'
    })()`],
    context: `${context} long title`,
    initScript,
    log,
    session,
  })
  await runAgentBrowser({ args: ['wait', '100'], context: `${context} reflow settle`, initScript, log, session })
  const wrapped = await assertLayoutGeometry({ context: `${context} wrapped title`, initScript, log, session })
  assert.ok(
    wrapped.headerHeight > base.headerHeight + 1,
    `${context}: header height did not follow title wrapping: ${JSON.stringify({ base, wrapped })}`,
  )
  assert.ok(
    wrapped.headerBottom < viewport.height * 0.75,
    `${context}: wrapped header leaves too little of the viewport for route content: ${JSON.stringify(wrapped)}`,
  )
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
