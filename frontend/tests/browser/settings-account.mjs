import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const SETTINGS_ROUTE = '/profile/settings'
const MUTATION_PATHS = [
  '/users/api/user_settings/',
  '/users/api/update_user_data_for_new_account/',
  '/users/api/update_dashboard_settings/',
]
const SAVED_UNAVAILABLE_MESSAGE =
  'Your saved account selection is unavailable. Choose an available account selection before saving.'
const REAL_OPTION_TITLES = [
  'All accounts',
  'First Broker – First account',
  'Second Broker – Second account',
  'All First Broker accounts',
  'Long Term',
]

// Counts real POSTs only: CORS preflights carry fixtureMethod POST too, so
// the actualMethod is the only reliable request marker.
const mutationCount = (fixtureServer) =>
  fixtureServer.requests.filter(
    (request) => request.actualMethod === 'POST' && MUTATION_PATHS.includes(request.path)
  ).length

const evalProbe = async (run, expression) => (await run(['eval', expression])).result

const waitFor = (run, fn, timeout = 12000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

// One probe for the whole corrected surface: the account select's visible
// label AND underlying input value, its associated messages, the Save
// button's disabled/hittable state, and raw-object leakage anywhere.
// Hit-testing must use controls a user can actually reach: each target is
// scrolled to viewport center and, if a fixed overlay (the taller-at-zoom app
// bar) still covers it, the page nudges so the control drops below it — the
// D3/D4 toolbar lesson. Unreachable controls fail the probe honestly.
const STATE_PROBE = `(() => {
  // Returns 'hittable' (the control itself receives the point), the tolerated
  // 'visible-disabled' (Vuetify disabled buttons use pointer-events: none, so
  // the point lands on the control's own container — visible but correctly
  // inert), or 'covered' (an unrelated overlay wins, a real defect).
  const hittable = (el, disabledOk) => {
    el.scrollIntoView({ block: 'center' })
    for (let attempt = 0; attempt < 6; attempt++) {
      const rect = el.getBoundingClientRect()
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
      if (el.contains(hit) || hit === el) return 'hittable'
      if (disabledOk && hit && (hit.contains(el) || (el.parentElement && el.parentElement.contains(hit)))) {
        return 'visible-disabled'
      }
      // Below the fold: scroll down to reach it; otherwise nudge up so a
      // fixed header overlay releases the control.
      if (rect.top >= window.innerHeight) window.scrollBy(0, rect.top - window.innerHeight + rect.height + 24)
      else window.scrollBy(0, -90)
    }
    return 'covered'
  }
  const input = [...document.querySelectorAll('.v-input')].find((el) =>
    [...el.querySelectorAll('.v-label')].some((label) => label.textContent.trim() === 'Default Account Selection'))
  const button = [...document.querySelectorAll('button')].find((el) => el.textContent.trim() === 'Save Settings')
  const state = {
    selectFound: !!input,
    label: null,
    value: null,
    messages: [],
    fieldHit: null,
    saveFound: !!button,
    saveDisabled: null,
    saveHit: null,
    rawObjectAnywhere: document.body.innerText.includes('[object Object]'),
    jsonAnywhere: document.body.innerText.includes('"type"'),
    savedSuccessfullyAnywhere: document.body.innerText.includes('Settings saved successfully'),
  }
  if (input) {
    state.label = input.querySelector('.v-select__selection')?.textContent.trim() ?? null
    state.value = input.querySelector('input')?.value ?? null
    state.messages = [...input.querySelectorAll('.v-messages__message')].map((m) => m.textContent.trim())
    const field = input.querySelector('.v-field')
    if (field) state.fieldHit = hittable(field, false)
  }
  if (button) {
    state.saveDisabled = button.disabled
    state.saveHit = hittable(button, button.disabled)
    if (state.saveHit === 'covered') {
      const rect = button.getBoundingClientRect()
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
      state.saveHitDebug = {
        tag: hit ? hit.tagName : null,
        cls: hit ? String(hit.className).slice(0, 120) : null,
        buttonRect: { top: Math.round(rect.top), left: Math.round(rect.left), w: Math.round(rect.width), h: Math.round(rect.height) },
        scrollY: Math.round(window.scrollY),
        innerH: window.innerHeight,
        docH: document.documentElement.scrollHeight,
      }
    }
  }
  return state
})()`

const LOADING_PROBE = `(() => ({
  spinner: !!document.querySelector('.v-progress-circular'),
  form: !!document.querySelector('form'),
}))()`

const HEADER_LABEL_PROBE = `(() => ({
  label: document.querySelector('.account-selection .v-select__selection')?.textContent.trim() ?? null,
}))()`

const MENU_OPEN_PROBE = `(() => ({
  open: !!document.querySelector('.v-overlay--active .v-list'),
}))()`

const assertUnavailableState = (state, phase) => {
  assert.equal(state.selectFound, true, `${phase}: account select rendered`)
  assert.equal(state.label, 'Unavailable', `${phase}: visible label`)
  assert.equal(state.value, 'Unavailable', `${phase}: exact input value`)
  assert.deepEqual(state.messages, [SAVED_UNAVAILABLE_MESSAGE], `${phase}: persistent explanation`)
  assert.equal(state.saveFound, true, `${phase}: Save button rendered`)
  assert.equal(state.saveDisabled, true, `${phase}: Save disabled while unresolved`)
  assert.equal(state.fieldHit, 'hittable', `${phase}: account field is hittable`)
  assert.equal(state.saveHit, 'visible-disabled', `${phase}: Save visible but correctly inert`)
  assert.equal(state.rawObjectAnywhere, false, `${phase}: no raw object text`)
  assert.equal(state.jsonAnywhere, false, `${phase}: no raw JSON text`)
}

async function clickNamedControl(run, role, name) {
  // Vuetify teleports menus and animates them into place; retry until the
  // named control exists and accepts the click.
  let lastError
  for (let attempt = 0; attempt < 12; attempt++) {
    const snapshot = await run(['snapshot', '-i'])
    const ref = Object.entries(snapshot.refs).find(
      ([, item]) => item.role === role && item.name.toLowerCase() === name.toLowerCase()
    )?.[0]
    if (ref) {
      try {
        await run(['click', `@${ref}`])
        return
      } catch (error) {
        if (!String(error.message).includes('is covered by')) throw error
        lastError = error
      }
    } else {
      lastError = new Error(`Missing ${role} ${name}`)
    }
    await run(['wait', '100'])
  }
  assert.fail(lastError?.message ?? `Could not click ${role} ${name}`)
}

const clickAccountField = (run) =>
  evalProbe(run, `(() => {
    const input = [...document.querySelectorAll('.v-input')].find((el) =>
      [...el.querySelectorAll('.v-label')].some((label) => label.textContent.trim() === 'Default Account Selection'))
    if (!input) return false
    input.querySelector('.v-field').click()
    return true
  })()`)

const setDigits = (run, value) =>
  evalProbe(run, `(() => {
    const field = [...document.querySelectorAll('.v-input')].find((el) =>
      [...el.querySelectorAll('.v-label')].some((label) => label.textContent.trim() === 'Number of digits'))
    if (!field) return null
    const native = field.querySelector('input')
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    setter.call(native, '${value}')
    native.dispatchEvent(new Event('input', { bubbles: true }))
    return native.value
  })()`)

const clickSave = (run) =>
  evalProbe(run, `(() => {
    const button = [...document.querySelectorAll('button')].find((el) => el.textContent.trim() === 'Save Settings')
    if (!button) return false
    button.click()
    return true
  })()`)

const dispatchFormSubmit = (run) =>
  evalProbe(run, `(() => {
    const form = document.querySelector('form')
    if (!form) return false
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    return true
  })()`)

const runNativeZoom = (appOrigin, cdpUrl, percent) =>
  new Promise((resolveSpawn, rejectSpawn) => {
    const child = spawn(
      process.execPath,
      [resolve(here, '../../scripts/qa-native-zoom.mjs'), String(cdpUrl), appOrigin, String(percent)],
      { stdio: 'pipe' }
    )
    let out = ''
    child.stdout.on('data', (chunk) => { out += chunk })
    child.stderr.on('data', (chunk) => { out += chunk })
    child.on('error', rejectSpawn)
    child.on('close', (code) => resolveSpawn({ code, out }))
  })

async function assertZeroWriteSubmissions(run, fixtureServer, phase) {
  const before = mutationCount(fixtureServer)
  assert.equal(await clickSave(run), true, `${phase}: Save button clickable (no-op while disabled)`)
  assert.equal(await dispatchFormSubmit(run), true, `${phase}: form submit dispatched`)
  await run(['wait', '400'])
  assert.equal(
    mutationCount(fixtureServer),
    before,
    `${phase}: attempted unresolved submissions must produce zero writes`
  )
}

async function openAccountMenu(run) {
  // A real agent-browser click both opens the menu AND focuses the field, so
  // the keyboard phase can navigate; the synthetic field click is only the
  // fallback (menu toggling itself does not need focus).
  try {
    await clickNamedControl(run, 'combobox', 'Default Account Selection')
  } catch {
    assert.equal(await clickAccountField(run), true, 'account field clickable')
  }
  await run(['wait', '350'])
  let menu = await evalProbe(run, MENU_OPEN_PROBE)
  if (!menu.open) {
    assert.equal(await clickAccountField(run), true, 'account field clickable')
    await run(['wait', '350'])
    menu = await evalProbe(run, MENU_OPEN_PROBE)
  }
  assert.equal(menu.open, true, 'account menu opened')
}

async function selectMenuOption(run, title) {
  await openAccountMenu(run)
  await clickNamedControl(run, 'option', title)
  await run(['wait', '350'])
}

async function runFullDesktopFlow({ run, fixtureServer, appOrigin, initScript, log, session }) {
  // --- 1. Initial unavailable state ---------------------------------------
  await run(['wait', '400'])
  assertUnavailableState(await evalProbe(run, STATE_PROBE), 'initial load')

  // --- 2. Unresolved submissions produce zero writes -----------------------
  await assertZeroWriteSubmissions(run, fixtureServer, 'initial unresolved state')

  // --- 3. Delayed initial load: loading state, then the same honesty -------
  fixtureServer.holdSettingsChoices()
  await run(['open', `${appOrigin}${SETTINGS_ROUTE}`])
  await run(['wait', '500'])
  const loading = await evalProbe(run, LOADING_PROBE)
  assert.equal(loading.spinner, true, 'delayed load: spinner shown')
  assert.equal(loading.form, false, 'delayed load: form hidden')
  fixtureServer.releaseRead('/users/api/user_settings_choices/')
  await run(['wait', '600'])
  assertUnavailableState(await evalProbe(run, STATE_PROBE), 'after delayed load')

  // --- 4. Native 200% zoom: controls and message stay visible/hittable -----
  const cdpInfo = await runAgentBrowser({
    args: ['get', 'cdp-url'],
    context: 'settings account cdp',
    initScript,
    log,
    session,
  })
  const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
  const zoom = await runNativeZoom(appOrigin, cdpUrl, 200)
  assert.equal(zoom.code, 0, `native 200% zoom must be dpr-verified (${zoom.out.trim()})`)
  await run(['wait', '400'])
  assertUnavailableState(await evalProbe(run, STATE_PROBE), 'native 200% zoom')
  const zoomReset = await runNativeZoom(appOrigin, cdpUrl, 100)
  assert.equal(zoomReset.code, 0, `zoom reset must restore dpr 1 (${zoomReset.out.trim()})`)
  await run(['wait', '300'])

  // --- 5. Keyboard resolution: open, ArrowDown, Enter ----------------------
  const writesBeforeKeyboard = mutationCount(fixtureServer)
  await openAccountMenu(run)
  await run(['press', 'ArrowDown'])
  await run(['press', 'Enter'])
  await run(['wait', '350'])
  const keyboardState = await evalProbe(run, STATE_PROBE)
  assert.equal(keyboardState.saveDisabled, false, 'keyboard selection resolves the field')
  assert.deepEqual(keyboardState.messages, [], 'availability warning clears after a real selection')
  assert.ok(
    REAL_OPTION_TITLES.includes(keyboardState.label),
    `keyboard selection lands on a real option (${keyboardState.label})`
  )
  assert.equal(keyboardState.value, keyboardState.label, 'keyboard selection: input value matches label')
  assert.equal(
    mutationCount(fixtureServer),
    writesBeforeKeyboard,
    'keyboard selection alone writes nothing'
  )

  // --- 6. Explicit real account through the rendered select, saved ---------
  await selectMenuOption(run, 'Second Broker – Second account')
  const selected = await evalProbe(run, STATE_PROBE)
  assert.equal(selected.label, 'Second Broker – Second account', 'explicit selection label')
  assert.equal(selected.value, 'Second Broker – Second account', 'explicit selection input value')
  assert.equal(selected.saveDisabled, false, 'Save enabled after explicit selection')
  assert.equal(selected.saveHit, 'hittable', 'enabled Save is hittable')
  assert.equal(await setDigits(run, '5'), '5', 'digits edited')

  const writesBeforeFirstSave = mutationCount(fixtureServer)
  assert.equal(await clickSave(run), true, 'Save clicked')
  await waitFor(run, `(() => document.body.innerText.includes('Settings saved successfully'))()`)
  await run(['wait', '400'])
  const settings = fixtureServer.settingsAccount
  assert.equal(settings.profileWrites.length, 1, 'exactly one profile write')
  const profileBody = settings.profileWrites[0]
  for (const key of ['selected_account', 'selected_account_type', 'selected_account_id', 'default_currency', 'digits'])
    assert.equal(Object.hasOwn(profileBody, key), false, `profile payload excludes context-owned ${key}`)
  assert.equal(profileBody.use_default_currency_where_relevant, true)
  assert.equal(profileBody.chart_frequency, 'M')
  assert.equal(profileBody.chart_timeline, 'YTD')
  assert.equal(profileBody.NAV_barchart_default_breakdown, 'none')
  assert.deepEqual(settings.accountWrites, [{ type: 'account', id: 2 }], 'context queue got the explicit identity')
  assert.deepEqual(
    settings.dashboardWrites,
    [{ table_date: '2026-09-08', default_currency: 'USD', digits: 5 }],
    'context queue got the edited digits'
  )
  assert.equal(mutationCount(fixtureServer) - writesBeforeFirstSave, 3, 'exactly three mutation POSTs')

  // Readback on the dashboard: the profile page hides the header context
  // strip by design, so the committed selection is verified where it renders.
  await run(['open', `${appOrigin}/dashboard`])
  await run(['wait', '700'])
  assert.equal(
    (await evalProbe(run, HEADER_LABEL_PROBE)).label,
    'Second Broker – Second account',
    'readback: the header shows the saved selection'
  )

  // --- 7. Rejected profile write: honest error, retained edits, retry ------
  await run(['open', `${appOrigin}${SETTINGS_ROUTE}`])
  await run(['wait', '700'])
  const reloaded = await evalProbe(run, STATE_PROBE)
  assert.equal(reloaded.label, 'Second Broker – Second account', 'reloaded form shows the saved selection')
  assert.equal(reloaded.saveDisabled, false, 'reloaded resolved form can save')
  await run(['wait', '3300'])
  const successCountBeforeRejection = (await evalProbe(run, STATE_PROBE)).savedSuccessfullyAnywhere
  assert.equal(successCountBeforeRejection, false, 'success snackbar expired before the rejection phase')
  fixtureServer.queueProfileRejection()
  assert.equal(await setDigits(run, '6'), '6', 'digits edited before the rejected save')
  assert.equal(await clickSave(run), true, 'Save clicked for the rejected profile write')
  await waitFor(run, `(() => document.body.innerText.includes('Please correct the errors in the form.'))()`)
  await run(['wait', '400'])
  const rejected = await evalProbe(run, STATE_PROBE)
  assert.equal(settings.profileWrites.length, 2,
    'the rejected profile write reached the profile endpoint exactly once')
  assert.equal(fixtureServer.settingsAccount.accountWrites.length, 1,
    'a rejected profile write never reaches the context queue')
  assert.equal(rejected.savedSuccessfullyAnywhere, false, 'no success message on rejection')
  assert.equal(
    (await evalProbe(run, `(() => ({ visible: document.body.innerText.includes('Synthetic breakdown rejection') }))()`)).visible,
    true,
    'the server field rejection is visible on the field'
  )
  assert.equal(rejected.value, 'Second Broker – Second account', 'selection retained after rejection')
  assert.equal(rejected.saveDisabled, false, 'Save re-enabled after the rejection settled')

  assert.equal(await clickSave(run), true, 'retry after the rejected profile write')
  await waitFor(run, `(() => document.body.innerText.includes('Settings saved successfully'))()`)
  await run(['wait', '400'])
  assert.equal(fixtureServer.settingsAccount.accountWrites.length, 2, 'retry saves the retained identity')
  assert.deepEqual(fixtureServer.settingsAccount.dashboardWrites[1],
    { table_date: '2026-09-08', default_currency: 'USD', digits: 6 }, 'retry carries the corrected digits')

  // --- 8. Rejected context write: honest error, no success, retry ----------
  await run(['wait', '3300'])
  fixtureServer.queueContextRejection()
  assert.equal(await clickSave(run), true, 'Save clicked for the rejected context write')
  await waitFor(run, `(() => document.body.innerText.includes('Failed to save settings. Please try again.'))()`)
  await run(['wait', '400'])
  const contextRejected = await evalProbe(run, STATE_PROBE)
  assert.equal(fixtureServer.settingsAccount.profileWrites.length, 4, 'the profile write of the failed sequence happened once')
  assert.equal(fixtureServer.settingsAccount.accountWrites.length, 3, 'the context mutation was attempted exactly once')
  assert.equal(fixtureServer.settingsAccount.dashboardWrites.length, 2,
    'a rejected account mutation never reaches the dashboard settings write')
  assert.equal(contextRejected.savedSuccessfullyAnywhere, false, 'no success message on context rejection')
  assert.equal(contextRejected.value, 'Second Broker – Second account', 'selection retained after context rejection')
  assert.equal(contextRejected.saveDisabled, false, 'Save re-enabled after the failed sequence')

  assert.equal(await clickSave(run), true, 'retry after the rejected context write')
  await waitFor(run, `(() => document.body.innerText.includes('Settings saved successfully'))()`)
  await run(['wait', '400'])
  assert.deepEqual(fixtureServer.settingsAccount.accountWrites[3], { type: 'account', id: 2 },
    'retry saves the same explicit identity')

  // --- 9. Explicit All accounts is a real, savable choice ------------------
  await run(['wait', '3300'])
  await selectMenuOption(run, 'All accounts')
  const allSelected = await evalProbe(run, STATE_PROBE)
  assert.equal(allSelected.label, 'All accounts', 'explicit All accounts label')
  assert.equal(allSelected.value, 'All accounts', 'explicit All accounts input value')
  assert.deepEqual(allSelected.messages, [], 'no availability warning for a resolved all selection')
  assert.equal(allSelected.saveDisabled, false, 'Save enabled for the explicit all selection')
  assert.equal(await clickSave(run), true, 'Save clicked for the all selection')
  await waitFor(run, `(() => document.body.innerText.includes('Settings saved successfully'))()`)
  await run(['wait', '400'])
  assert.deepEqual(fixtureServer.settingsAccount.accountWrites[4], { type: 'all', id: null },
    'the explicit all identity reaches the context queue unchanged')
  await run(['open', `${appOrigin}/dashboard`])
  await run(['wait', '700'])
  assert.equal(
    (await evalProbe(run, HEADER_LABEL_PROBE)).label,
    'All accounts',
    'readback: the header shows the all selection'
  )

  // --- 10. Final page-error sweep ------------------------------------------
  const errorData = await run(['errors'])
  assert.deepEqual(errorData.errors, [], 'no page errors across the whole flow')
  await log({ context: 'settings account full flow', status: 'passed' })
}

async function runMobileUnavailableCheck({ run, fixtureServer, appOrigin }) {
  // A fresh 390px session must see the same honest unresolved state, with
  // hittable controls and zero writes for attempted submissions. The saved
  // identity is reset server-side so this session loads the missing one.
  fixtureServer.resetSettingsAccount()
  await run(['open', `${appOrigin}${SETTINGS_ROUTE}`])
  await run(['wait', '700'])
  assertUnavailableState(await evalProbe(run, STATE_PROBE), 'mobile 390px')
  await assertZeroWriteSubmissions(run, fixtureServer, 'mobile 390px')
}

export async function assertSettingsAccountFlow({
  appOrigin,
  context,
  initScript,
  log,
  session,
  fixtureServer,
  viewport,
}) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  if (viewport.name === 'desktop') {
    await runFullDesktopFlow({ run, fixtureServer, appOrigin, initScript, log, session })
    console.log(`PASS ${context} desktop flow`)
  } else if (viewport.name === 'mobile') {
    await runMobileUnavailableCheck({ run, fixtureServer, appOrigin })
    console.log(`PASS ${context} mobile unavailable check`)
  }
}
