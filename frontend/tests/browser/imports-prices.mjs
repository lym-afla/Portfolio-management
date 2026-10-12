import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

/**
 * Price-import acceptance over the REAL transport in the REAL browser
 * (Task 3, real-data corrections): the mounted dialog drives the actual
 * axios SSE request against the fixture's scripted streams. Covers the
 * exact multi-account payload, the readable progress label while the
 * stream is live, the completion summary, the explicit no-eligible result,
 * the provider-error surface and the transport-abort surface.
 *
 * Dialog interaction follows the d7 pattern: the dialog lives in a
 * teleported overlay where a11y clicks do not open the menus — dispatched
 * pointer events on the field's input open them and dispatched clicks
 * choose the rendered options. The multiple accounts menu stays open
 * across picks (an Escape closes the WHOLE dialog); the single frequency
 * select closes itself (an extra Escape would close the dialog too).
 */
export async function runImportsPricesFlow({
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

  const openDialog = async () => {
    await run(['open', `${appOrigin}/database/prices`])
    for (let attempt = 0; attempt < 30; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const refs = Object.entries(snapshot.refs).filter(
        ([, item]) => item.role === 'button' && (item.name ?? '').trim().toLowerCase() === 'import prices'
      )
      if (refs.length > 0) {
        try {
          await run(['click', '@' + refs[0][0]])
          await run(['wait', '600'])
          const open = await evalP(
            `(() => { const card = document.querySelector('.v-dialog.v-overlay--active .v-card'); return card ? card.innerText.includes('Import Prices') : false })()`
          )
          if (open === true) return
        } catch (error) {
          if (!String(error.message).includes('is covered by')) throw error
        }
      }
      await run(['wait', '300'])
    }
    assert.fail('the price-import dialog did not open')
  }

  // d7-pattern field interaction: dispatched pointer events on the field's
  // input open the menu; the option is chosen by a dispatched click.
  const pickOption = async (fieldLabel, optionName, { keepOpen = false } = {}) => {
    const opened = await evalP(`(() => {
      const dialog = document.querySelector('.v-dialog.v-overlay--active')
      if (!dialog) return false
      const field = [...dialog.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')]
          .some((l) => l.textContent.trim() === ${JSON.stringify(fieldLabel)}))
      if (!field) return false
      field.scrollIntoView({ block: 'center' })
      const target = field.querySelector('input') ?? field.querySelector('.v-field') ?? field
      target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
      target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      return true
    })()`)
    assert.equal(opened, true, `${fieldLabel}: field found in the dialog`)
    await run(['wait', '700'])
    let chosen = null
    for (let attempt = 0; attempt < 10 && chosen === null; attempt++) {
      chosen = await evalP(`(() => {
        const options = [
          ...document.querySelectorAll('.v-overlay .v-list-item'),
          ...document.querySelectorAll('[role="option"]'),
        ]
        const option = options.find((o) => o.textContent.includes(${JSON.stringify(optionName)}))
        if (!option) return null
        option.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
        option.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        return true
      })()`)
      if (chosen === null) await run(['wait', '300'])
    }
    assert.equal(chosen, true, `${fieldLabel}: option ${optionName} chosen`)
    if (!keepOpen) return
    // keepOpen still means "do not press Escape" — the caller closes the
    // menu explicitly at the right moment.
  }

  const fillAndSubmit = async () => {
    // The dialog enforces securities XOR accounts (selecting one disables
    // the other), so the account-based path pins both account identities
    // through the real transport.
    await pickOption('Accounts', 'Fixture Trading', { keepOpen: true })
    await pickOption('Accounts', 'Fixture Long-term', { keepOpen: true })
    await run(['press', 'Escape'])
    await run(['wait', '400'])
    // The single frequency select closes its own menu on choice.
    await pickOption('Frequency', 'Weekly', { keepOpen: true })
    // Dates: the inline calendars render in the dialog; pick October 1 and
    // October 28 so the range validates.
    await clickInDialogDay('October 1,', 'start-day cell')
    await clickInDialogDay('October 28,', 'end-day cell')
    const before = fixtureServer.priceImport.requests.length
    await clickInScopeButton('Import Prices', 'dialog submit button')
    // Wait until the transport actually fires the SSE POST (validation
    // passed) before any post-submit assertion.
    for (let attempt = 0; attempt < 50; attempt++) {
      if (fixtureServer.priceImport.requests.length > before) break
      await run(['wait', '100'])
    }
    if (fixtureServer.priceImport.requests.length === before) {
      const state = await evalP(`document.querySelector('.v-dialog') ? document.querySelector('.v-dialog').innerText.slice(0, 300) : 'no dialog'`)
      await log({ submitMiss: state, status: 'submit-miss' })
      assert.fail('the submit never fired the SSE request: ' + JSON.stringify(state))
    }
    await run(['wait', '400'])
    return before
  }

  const clickInDialogDay = async (nameMatch, label) => {
    for (let attempt = 0; attempt < 15; attempt++) {
      const snapshot = await run(['snapshot', '-i', '-s', '.v-dialog.v-overlay--active'])
      const ref = Object.entries(snapshot.refs).find(
        ([, item]) => item.role === 'button' && String(item.name ?? '').toLowerCase().includes(nameMatch.toLowerCase())
      )?.[0]
      if (ref) {
        try {
          await run(['click', '@' + ref])
          return
        } catch (error) {
          if (!String(error.message).includes('is covered by')) throw error
        }
      }
      await run(['wait', '200'])
    }
    assert.fail(`Missing ${label}`)
  }

  const clickInScopeButton = async (nameMatch, label) => {
    for (let attempt = 0; attempt < 15; attempt++) {
      const snapshot = await run(['snapshot', '-i', '-s', '.v-dialog.v-overlay--active'])
      const ref = Object.entries(snapshot.refs).find(
        ([, item]) => item.role === 'button' && String(item.name ?? '').toLowerCase().includes(nameMatch.toLowerCase())
      )?.[0]
      if (ref) {
        try {
          await run(['click', '@' + ref])
          return
        } catch (error) {
          if (!String(error.message).includes('is covered by')) throw error
        }
      }
      await run(['wait', '200'])
    }
    assert.fail(`Missing ${label}`)
  }

  const openAndSubmit = async () => {
    await openDialog()
    return fillAndSubmit()
  }

  const closeOverlay = async () => {
    await run(['press', 'Escape'])
    await run(['wait', '700'])
  }

  // --- Happy path: multi-account payload, readable live progress, summary --
  fixtureServer.priceImport.scenario = 'slow'
  const submitBefore = await openAndSubmit()
  await waitFor(
    `document.querySelector('[data-testid="import-progress-label"]') !== null`
  )
  const progressState = await evalP(`(() => {
    const label = document.querySelector('[data-testid="import-progress-label"]')
    return {
      text: label ? label.innerText : null,
      inFill: label ? label.closest('.v-progress-linear') !== null : null,
      body2: label ? label.querySelectorAll('.text-body-2').length : 0,
    }
  })()`)
  assert.match(String(progressState.text), /\d+%/, `the live progress label carries the percentage: ${JSON.stringify(progressState)}`)
  assert.equal(progressState.inFill, false, 'the progress label sits outside the moving fill')
  assert.ok(progressState.body2 >= 2, 'the label is body-size themed text, not in-bar styling')
  const payload = fixtureServer.priceImport.requests[submitBefore]
  assert.deepEqual(payload.accounts, [7, 11], `the transport carries the exact selected accounts: ${JSON.stringify(payload)}`)
  assert.equal(payload.frequency, 'weekly')
  await waitFor(`document.body.innerText.includes('Import Summary')`)
  assert.equal(
    await evalP(`document.body.innerText.includes('Total securities processed: 1')`),
    true,
    'the completion summary renders the import totals'
  )
  await log({ context, happyPath: { payload, progressState }, status: 'passed' })
  await closeOverlay()

  // --- No eligible holdings: explicit info result ---------------------------
  fixtureServer.priceImport.scenario = 'no-eligible'
  await openAndSubmit()
  await waitFor(`document.querySelector('[data-testid="no-eligible-securities"]') !== null`)
  const noEligible = await evalP(`document.querySelector('[data-testid="no-eligible-securities"]')?.innerText ?? null`)
  assert.match(String(noEligible), /No eligible securities found/, 'the no-eligible completion is an explicit info result')
  await log({ context, noEligible: 'surfaced', status: 'passed' })
  await closeOverlay()

  // --- Provider error: the stream's error event surfaces --------------------
  fixtureServer.priceImport.scenario = 'provider-error'
  await openAndSubmit()
  await waitFor(`document.body.innerText.includes('Provider rejected the price request')`)
  await log({ context, providerError: 'surfaced', status: 'passed' })
  // The failed stream keeps the progress dialog open with the error alert;
  // the user closes it through the dialog's own Close action.
  await clickInScopeButton('Close', 'error dialog Close button')
  await run(['wait', '700'])

  // --- Transport abort: the axios failure surfaces through the error owner --
  fixtureServer.priceImport.scenario = 'abort'
  await openAndSubmit()
  await waitFor(`document.body.innerText.includes('No response received from server')`)
  await log({ context, transportAbort: 'surfaced', status: 'passed' })

  return {
    requests: fixtureServer.priceImport.requests.length,
    payload: fixtureServer.priceImport.requests[0],
  }
}
