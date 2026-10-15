import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'

const evalProbe = async (run, expression) => (await run(['eval', expression])).result
const waitFor = (run, fn, timeout = 20000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const CAPTURE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/design/assets/dashboard-summary-d',
)

// Phase D rendered acceptance: the approved reconciled statement driven
// against backend-faithful synthetic contract fixtures. Verifies actual
// rendered display strings, the single summary request owner, expanded and
// collapsed breakdown detail, honest partial/unreconciled/legacy/malformed
// states, long-amount containment (hit tests, not scrollWidth alone),
// desktop/tablet/mobile stacking, desktop-mobile-desktop transitions and
// native 200% zoom with DPR verification/reset. Retakes only this phase's
// synthetic assets under docs/design/assets/dashboard-summary-d/.
export async function runStatementDFlow({
  appOrigin,
  context,
  initScript,
  log,
  session,
  viewport,
  fixtureServer,
  frontendRoot,
}) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const isDesktop = viewport.name === 'desktop'
  const captureDir = resolve(CAPTURE_DIR)
  mkdirSync(captureDir, { recursive: true })
  const capture = async (name, expectedPath = '/dashboard') => {
    const location = await evalProbe(run, 'location.pathname')
    assert.equal(
      location,
      expectedPath,
      `${context}: capture ${name} must be taken on ${expectedPath}, saw ${location}`,
    )
    const path = resolve(captureDir, `statement-d-${name}.png`)
    await run(['screenshot', path])
    return path
  }

  const openDashboard = async (variant) => {
    fixtureServer.setStatementVariant(variant)
    await run(['open', `${appOrigin}/dashboard`])
    if (variant === 'legacy_only') {
      await waitFor(run, `document.body.innerText.includes('Total NAV')`)
    } else if (variant === 'malformed') {
      // v-btn labels are CSS-uppercased; innerText reads 'RETRY'.
      await waitFor(run, `document.body.innerText.toLowerCase().includes('retry')`)
    } else {
      await waitFor(
        run,
        `document.body.innerText.includes('Net invested capital')`,
      )
    }
    await run(['wait', '300'])
  }

  const statementText = () =>
    evalProbe(
      run,
      `document.querySelector('[data-testid="portfolio-statement-section"]')?.innerText.replace(/\\n/g, ' | ') ?? null`,
    )

  const breakdownVisible = () =>
    evalProbe(
      run,
      `(() => { const el = document.querySelector('[data-testid="net-result-breakdown"]'); return el ? el.style.display !== 'none' : null })()`,
    )

  // Probe geometry: statement/returns containment, stacking, hit tests and
  // body-level horizontal overflow. elementFromPoint hit tests prove the
  // values are actually visible, not just present in the DOM.
  const geometry = () =>
    evalProbe(run, `(() => {
      const section = document.querySelector('[data-testid="portfolio-statement-section"]')
      if (!section) return { present: false }
      const nav = document.querySelector('.statement-row.total-row dd')
      const navRect = nav ? nav.getBoundingClientRect() : null
      const navHit = navRect ? (() => {
        const cx = Math.round(navRect.left + navRect.width / 2)
        const cy = Math.round(navRect.top + navRect.height / 2)
        const hit = document.elementFromPoint(cx, cy)
        return !!hit && (!!nav.contains(hit) || !!hit.closest('.total-row'))
      })() : null
      const returns = document.querySelector('.returns')
      const statement = document.querySelector('.statement')
      const dds = [...section.querySelectorAll('dd')]
      return {
        present: true,
        sectionRight: Math.round(section.getBoundingClientRect().right),
        sectionLeft: Math.round(section.getBoundingClientRect().left),
        viewportW: window.innerWidth,
        navText: nav ? nav.innerText.trim() : null,
        navHit,
        navClipped: nav ? nav.scrollWidth > nav.clientWidth + 1 : null,
        returnsTop: returns ? Math.round(returns.getBoundingClientRect().top) : null,
        statementTop: statement ? Math.round(statement.getBoundingClientRect().top) : null,
        statementBottom: statement ? Math.round(statement.getBoundingClientRect().bottom) : null,
        anyClipped: dds.some((dd) => dd.scrollWidth > dd.clientWidth + 1),
        anyOutside: dds.some((dd) => {
          const r = dd.getBoundingClientRect()
          return r.right > window.innerWidth + 1 || r.left < -1
        }),
        bodyScrollX: document.documentElement.scrollWidth > window.innerWidth + 1,
      }
    })()`)

  const clickTestid = (testid) =>
    evalProbe(
      run,
      `(() => { const el = document.querySelector('[data-testid="${testid}"]'); if (!el) return false; el.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true })()`,
    )

  const toggleProbe = () =>
    evalProbe(run, `(() => {
      const toggle = document.querySelector('[data-testid="breakdown-toggle"]')
      if (!toggle) return { present: false }
      const rect = toggle.getBoundingClientRect()
      const cx = Math.round(rect.left + rect.width / 2)
      const cy = Math.round(rect.top + rect.height / 2)
      const hit = document.elementFromPoint(cx, cy)
      return {
        present: true,
        ariaExpanded: toggle.getAttribute('aria-expanded'),
        hitInside: !!hit && (!!toggle.contains(hit) || hit === toggle),
        rectTop: Math.round(rect.top),
        rectHeight: Math.round(rect.height),
      }
    })()`)

  // ---------------- reconciled (approved composition) ----------------
  fixtureServer.setStatementVariant('reconciled')
  // runRoute already loaded /dashboard once and its summary request may
  // still be in flight; settle this load first so every assertion below
  // counts clean DELTAS from the snapshot (observed straggler at tablet).
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.body.innerText.includes('Net invested capital')`)
  await run(['wait', '400'])
  const requestsBefore = fixtureServer.statementD.requests.length
  await run(['open', `${appOrigin}/dashboard`])
  await waitFor(run, `document.body.innerText.includes('Net invested capital')`)
  await run(['wait', '400'])

  const reconciled = await statementText()
  for (const needle of [
    'Invested', '$100,000.00',
    'Cash out', '($5,000.00)',
    'Net invested capital', '$95,000.00',
    'Net result', '$17,500.00',
    'Realized gains / losses', '$8,000.00',
    'Unrealized gains / losses', '$7,000.00',
    'Dividends & interest', '$3,500.00',
    'Fees', '($1,000.00)',
    'Taxes', '($500.00)',
    'FX effect', '$500.00',
    'Total NAV', '$112,500.00',
    'Price gains exclude FX; FX shown separately.',
  ]) {
    assert.ok(
      reconciled.includes(needle),
      `${context}: statement must render ${JSON.stringify(needle)}; got ${JSON.stringify(reconciled)}`,
    )
  }
  const returnsText = await evalProbe(
    run,
    `document.querySelector('.returns')?.innerText.replace(/\\n/g, ' | ') ?? null`,
  )
  assert.ok(returnsText.includes('Total return'), `${context}: returns card label`)
  assert.ok(returnsText.includes('17.5%'), `${context}: total return display`)
  assert.ok(returnsText.includes('Since inception'), `${context}: total return horizon`)
  assert.ok(returnsText.includes('IRR since inception'), `${context}: IRR label`)
  assert.ok(returnsText.includes('8.4%'), `${context}: IRR display`)

  // Chart coexistence: NAV chart and allocation sections stay on the page.
  const coexistence = await evalProbe(run, `(() => ({
    navPanel: !!document.querySelector('[data-testid="nav-chart-panel"]'),
    allocation: !!document.querySelector('[data-testid="allocation-section"]'),
    history: !!document.querySelector('[data-testid="history-section"]'),
    contextLabel: !!document.querySelector('[data-testid="portfolio-context-label"]'),
  }))()`)
  assert.equal(coexistence.navPanel, true, `${context}: NAV chart coexists`)
  assert.equal(coexistence.allocation, true, `${context}: allocation coexists`)
  assert.equal(coexistence.history, true, `${context}: history coexists`)
  assert.equal(coexistence.contextLabel, true, `${context}: context label present`)

  // Exactly ONE summary request carried the negotiation parameter.
  const summaryRequests = fixtureServer.statementD.requests.slice(requestsBefore)
  assert.equal(
    summaryRequests.length,
    1,
    `${context}: exactly one summary request per load expected, got ${summaryRequests.length}`,
  )
  assert.ok(
    summaryRequests[0].query.includes('summary_contract=2'),
    `${context}: the summary request must negotiate summary_contract=2, got ${summaryRequests[0].query}`,
  )

  // Expanded by default; toggle collapses and re-expands without a refetch.
  assert.equal(await breakdownVisible(), true, `${context}: breakdown starts expanded (approved image)`)
  const toggle = await toggleProbe()
  assert.equal(toggle.present, true, `${context}: breakdown toggle present`)
  assert.equal(toggle.ariaExpanded, 'true', `${context}: toggle aria-expanded`)
  assert.equal(toggle.hitInside, true, `${context}: toggle hit-test fails - covered or clipped`)
  assert.equal(await clickTestid('breakdown-toggle'), true, `${context}: toggle clickable`)
  await run(['wait', '150'])
  assert.equal(await breakdownVisible(), false, `${context}: collapse hides only the detail`)
  assert.equal(
    (await toggleProbe()).ariaExpanded,
    'false',
    `${context}: collapsed aria-expanded`,
  )
  assert.equal(
    fixtureServer.statementD.requests.length - requestsBefore,
    1,
    `${context}: toggling must not refetch the summary`,
  )
  // Keyboard: real Enter on the focused toggle re-expands.
  await clickTestid('breakdown-toggle')
  await run(['wait', '150'])
  assert.equal(await breakdownVisible(), true, `${context}: re-expanded for keyboard phase`)
  await evalProbe(run, `document.querySelector('[data-testid="breakdown-toggle"]').focus()`)
  await run(['press', 'Enter'])
  await run(['wait', '150'])
  assert.equal(await breakdownVisible(), false, `${context}: Enter collapses (keyboard operable)`)
  await evalProbe(run, `document.querySelector('[data-testid="breakdown-toggle"]').focus()`)
  await run(['press', 'Enter'])
  await run(['wait', '150'])
  assert.equal(await breakdownVisible(), true, `${context}: Enter re-expands`)

  // Complete state shows no status banner; amounts contained at this width.
  const reconciledGeometry = await geometry()
  assert.equal(reconciledGeometry.navHit, true, `${context}: NAV value hit-test fails`)
  assert.equal(reconciledGeometry.anyClipped, false, `${context}: clipped amounts`)
  assert.equal(reconciledGeometry.anyOutside, false, `${context}: amounts outside viewport`)
  assert.equal(reconciledGeometry.bodyScrollX, false, `${context}: horizontal body scroll`)
  const statusCount = await evalProbe(
    run,
    `document.querySelectorAll('[data-testid="statement-status"]').length`,
  )
  assert.equal(statusCount, 0, `${context}: complete statement shows no status banner`)

  await capture(`${viewport.name}`)

  // ---------------- partial (incomplete is visible, chart stays) -------
  if (isDesktop) {
    await openDashboard('partial')
    const partialStatus = await evalProbe(
      run,
      `document.querySelector('[data-testid="statement-status"]')?.innerText ?? null`,
    )
    assert.ok(
      partialStatus && partialStatus.includes('Partial statement') && partialStatus.includes('missing FX rates'),
      `${context}: partial state must be announced with its reason, got ${JSON.stringify(partialStatus)}`,
    )
    const partialFlag = await evalProbe(run, `(() => {
      const nav = document.querySelector('.statement-row.total-row dd')
      return nav ? nav.innerText.includes('(partial)') : null
    })()`)
    assert.equal(partialFlag, true, `${context}: partial NAV carries the (partial) flag`)
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="nav-chart-panel"]')`)),
      true,
      `${context}: chart stays in the partial state`,
    )
    await capture('partial')

    // ---------------- unreconciled (difference never hidden) ------------
    await openDashboard('unreconciled')
    const unreconciledStatus = await evalProbe(
      run,
      `document.querySelector('[data-testid="statement-status"]')?.innerText ?? null`,
    )
    assert.ok(
      unreconciledStatus && unreconciledStatus.includes('Unreconciled difference') && unreconciledStatus.includes('$500.00'),
      `${context}: unreconciled difference must be explicit, got ${JSON.stringify(unreconciledStatus)}`,
    )
    await clickTestid('breakdown-toggle')
    await run(['wait', '150'])
    assert.equal(
      (await evalProbe(
        run,
        `(() => { const el = document.querySelector('[data-testid="statement-status"]'); return el ? el.style.display !== 'none' : false })()`,
      )),
      true,
      `${context}: collapsing must not conceal the unreconciled state`,
    )
    await capture('unreconciled')

    // ---------------- legacy-only (honest five-metric fallback) --------
    await openDashboard('legacy_only')
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="portfolio-statement-section"]')`)),
      false,
      `${context}: legacy-only must not fabricate a statement`,
    )
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="summary-card"]')`)),
      true,
      `${context}: legacy five metrics stay`,
    )
    const legacyNotice = await evalProbe(
      run,
      `document.querySelector('[data-testid="statement-capability-notice"]')?.innerText ?? null`,
    )
    assert.ok(
      legacyNotice && legacyNotice.includes('reconciled statement is unavailable'),
      `${context}: honest legacy-only notice required, got ${JSON.stringify(legacyNotice)}`,
    )
    await capture('legacy-only')

    // ---------------- malformed (typed boundary, recovery) --------------
    await openDashboard('malformed')
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="summary-error"]')`)),
      true,
      `${context}: a present-but-invalid document must fail visibly`,
    )
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="portfolio-statement-section"]')`)),
      false,
      `${context}: no silent downgrade for a malformed document`,
    )
    fixtureServer.setStatementVariant('reconciled')
    await clickTestid('summary-retry')
    await waitFor(run, `document.body.innerText.includes('Net invested capital')`)
    assert.equal(
      (await evalProbe(run, `!!document.querySelector('[data-testid="portfolio-statement-section"]')`)),
      true,
      `${context}: retry recovers the statement`,
    )

    // ---------------- long exact amounts (containment + hit tests) -----
    await openDashboard('large')
    const largeGeometry = await geometry()
    assert.equal(largeGeometry.navText, '$123,456,789.01', `${context}: long NAV rendered verbatim`)
    assert.equal(largeGeometry.navHit, true, `${context}: long NAV hit-test fails`)
    assert.equal(largeGeometry.navClipped, false, `${context}: long NAV clipped inside its cell`)
    assert.equal(largeGeometry.anyClipped, false, `${context}: long amounts clipped`)
    assert.equal(largeGeometry.anyOutside, false, `${context}: long amounts outside viewport`)
    assert.equal(largeGeometry.bodyScrollX, false, `${context}: long amounts force body scroll`)
    await capture('large')

    // ---------------- native 200% zoom (DPR verified, then reset) -------
    const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: `${context} cdp`, initScript, log, session })
    const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
    assert.ok(cdpUrl, `${context}: cdp url available for the native zoom phase`)
    const zoomScript = resolve(frontendRoot, 'scripts', 'qa-native-zoom.mjs')
    const runZoom = (percent) =>
      new Promise((resolveZoom, rejectZoom) => {
        const child = spawn(process.execPath, [zoomScript, String(cdpUrl), appOrigin, String(percent)], { stdio: 'pipe' })
        let out = ''
        child.stdout.on('data', (chunk) => { out += chunk })
        child.stderr.on('data', (chunk) => { out += chunk })
        child.on('error', rejectZoom)
        child.on('close', (code) => {
          resolveZoom({ code, out })
        })
      })
    const zoomIn = await runZoom(200)
    assert.equal(zoomIn.code, 0, `${context}: native zoom to 200% failed: ${zoomIn.out}`)
    const dpr = await evalProbe(run, `window.devicePixelRatio`)
    assert.equal(Number(dpr), 2, `${context}: native zoom must move devicePixelRatio to 2, got ${dpr}`)
    await waitFor(run, `document.body.innerText.includes('Net invested capital')`)
    // At 200% the app bar is ~256 CSS px tall; bring the NAV row into the
    // viewport (below the bar) before hit-testing it.
    await evalProbe(run, `(() => {
      const row = document.querySelector('.statement-row.total-row')
      row?.scrollIntoView({ block: 'center' })
      const bar = document.querySelector('.v-app-bar')
      const barBottom = bar ? bar.getBoundingClientRect().bottom : 0
      const rect = row?.getBoundingClientRect()
      if (rect && rect.top < barBottom) window.scrollBy(0, barBottom - rect.top + 8)
      return true
    })()`)
    await run(['wait', '200'])
    const zoomGeometry = await geometry()
    assert.equal(zoomGeometry.navHit, true, `${context}: NAV hit-test fails at 200% zoom`)
    assert.equal(zoomGeometry.anyClipped, false, `${context}: clipped amounts at 200% zoom`)
    assert.equal(zoomGeometry.anyOutside, false, `${context}: amounts outside viewport at 200% zoom`)
    await capture('zoom-200')
    const zoomReset = await runZoom(100)
    assert.equal(zoomReset.code, 0, `${context}: zoom reset failed: ${zoomReset.out}`)
    const dprReset = await evalProbe(run, `window.devicePixelRatio`)
    assert.equal(Number(dprReset), 1, `${context}: zoom reset must restore devicePixelRatio, got ${dprReset}`)

    // ---------------- desktop -> mobile -> desktop transition -----------
    await run(['set', 'viewport', '390', '844'])
    await run(['wait', '300'])
    const mobileTransition = await geometry()
    assert.equal(mobileTransition.present, true, `${context}: statement survives the transition`)
    assert.equal(mobileTransition.bodyScrollX, false, `${context}: transition causes body scroll`)
    assert.equal(mobileTransition.anyOutside, false, `${context}: transition pushes amounts out`)
    assert.ok(
      mobileTransition.returnsTop >= mobileTransition.statementBottom - 2,
      `${context}: at 390px the returns card must stack below the statement`,
    )
    await run(['set', 'viewport', '1440', '1000'])
    await run(['wait', '300'])
    const backDesktop = await geometry()
    assert.ok(
      Math.abs(backDesktop.returnsTop - backDesktop.statementTop) < 40,
      `${context}: back at desktop the returns card returns beside the statement`,
    )
    assert.equal(backDesktop.bodyScrollX, false, `${context}: transition back causes body scroll`)
  } else if (viewport.name === 'mobile') {
    // Below 960px the sections stack.
    const stacked = await geometry()
    assert.equal(stacked.present, true, `${context}: statement present`)
    assert.ok(
      stacked.returnsTop >= stacked.statementBottom - 2,
      `${context}: returns must stack below the statement at ${viewport.width}px`,
    )
    assert.equal(stacked.anyClipped, false, `${context}: clipped amounts at ${viewport.width}px`)
    assert.equal(stacked.anyOutside, false, `${context}: amounts outside viewport at ${viewport.width}px`)
    assert.equal(stacked.bodyScrollX, false, `${context}: horizontal scroll at ${viewport.width}px`)
    assert.equal(stacked.navHit, true, `${context}: NAV hit-test fails at ${viewport.width}px`)
  } else {
    // Tablet: the two-column composition holds; amounts must stay contained.
    const tabletGeometry = await geometry()
    assert.equal(tabletGeometry.present, true, `${context}: statement present`)
    assert.equal(tabletGeometry.navHit, true, `${context}: NAV hit-test fails at ${viewport.width}px`)
    assert.equal(tabletGeometry.anyClipped, false, `${context}: clipped amounts at ${viewport.width}px`)
    assert.equal(tabletGeometry.anyOutside, false, `${context}: amounts outside viewport at ${viewport.width}px`)
    assert.equal(tabletGeometry.bodyScrollX, false, `${context}: horizontal scroll at ${viewport.width}px`)
  }
}
