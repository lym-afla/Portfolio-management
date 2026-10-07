import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

// C4 recorded a race where the Retry click landed while a Vuetify overlay
// scrim was still in its leave transition and covered the click point. The
// bounded synchronization below makes the harness await the real overlay
// transition (the control must be the element actually hit at its center)
// and retry a refused covered click briefly. Real clicks only — no force
// clicks, and every assertion stays: an unhittable control still fails the
// case after the bounded wait.
const waitHittable = (run, selector) =>
  run(['wait', '--fn', `(() => {
    const target = document.querySelector('${selector}')
    if (!target) return false
    const rect = target.getBoundingClientRect()
    if (rect.width < 1 || rect.height < 1) return false
    const hit = document.elementFromPoint(
      Math.min(Math.max(rect.left + rect.width / 2, 1), window.innerWidth - 1),
      Math.min(Math.max(rect.top + rect.height / 2, 1), window.innerHeight - 1),
    )
    return hit !== null && (hit === target || target.contains(hit) || hit.contains(target))
  })()`, '--timeout', '5000'])

/** Exercise real widget Retry controls with isolated loopback failure/success fixtures. */
export async function assertDashboardRecoveryFlow({ context, initScript, log, session, fixtureServer }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const widgets = [
    { id: 'summary', card: 'summary-card', path: '/dashboard/api/get-summary/', text: '$100.00' },
    { id: 'allocation-assetType', card: 'allocation-assetType-card', path: '/dashboard/api/get-breakdown/', text: 'Asset Type' },
    { id: 'history', card: 'history-table', path: '/dashboard/api/get-summary-over-time/', text: 'EoP NAV' },
    { id: 'nav', card: 'nav-chart', path: '/dashboard/api/get-nav-chart-data/', text: 'Value and return over time' },
  ]
  const count = (path) => fixtureServer.requests.filter((request) => request.actualMethod === 'GET' && request.path === path).length
  for (const widget of widgets) {
    fixtureServer.resetRecovery()
    await run(['reload'])
    await run(['wait', '--fn', `document.querySelector('[data-testid="${widget.id}-error"]') !== null`])
    const before = new Map(widgets.map((item) => [item.path, count(item.path)]))
    fixtureServer.recoverWidget(widget.path)
    await waitHittable(run, `[data-testid="${widget.id}-error"] button`)
    const snapshot = await run(['snapshot', '-i', '-s', `[data-testid="${widget.id}-error"]`])
    const retryRef = snapshot.snapshot.match(/button "RETRY" \[ref=([^\]]+)\]/i)?.[1]
    assert.ok(retryRef, `${widget.id} must expose its real Retry button`)
    let clicked = false
    let lastClickError = null
    for (let attempt = 0; attempt < 12 && !clicked; attempt++) {
      try {
        await run(['click', `@${retryRef}`])
        clicked = true
      } catch (error) {
        if (!error.message.includes('is covered by')) throw error
        lastClickError = error
        await waitHittable(run, `[data-testid="${widget.id}-error"] button`)
      }
    }
    if (!clicked) throw lastClickError ?? new Error(`${widget.id} Retry never became hittable`)
    await run(['wait', '--fn', `document.querySelector('[data-testid="${widget.card}"]') !== null && document.querySelector('[data-testid="${widget.id}-error"]') === null`])
    await run(['wait', '250'])
    const other = widget.id === 'summary' ? 'history' : 'summary'
    const state = (await run(['eval', `({ text: document.querySelector('[data-testid="${widget.card}"]')?.innerText, error: !!document.querySelector('[data-testid="${widget.id}-error"]'), otherError: !!document.querySelector('[data-testid="${other}-error"]'), canvas: !!document.querySelector('[data-testid="${widget.card}"] canvas') })`])).result
    assert.equal(state.error, false)
    assert.equal(state.otherError, true, 'retry must leave other widget failures visible')
    assert.ok(state.text.includes(widget.text), `${widget.id} accepted content must render`)
    if (widget.id === 'nav' || widget.id.startsWith('allocation')) assert.ok(state.canvas, 'actual chart must render')
    for (const item of widgets) assert.equal(count(item.path) - before.get(item.path), item.path === widget.path ? 1 : 0, 'retry must issue exactly one matching read')
    await log({ context, widget: widget.id, state, status: 'passed' })
  }
}
