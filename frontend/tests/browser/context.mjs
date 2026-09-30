import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'
export async function assertContextFailureFlow({
  context,
  initScript,
  log,
  session,
  fixtureServer,
}) {
  const run = (args) =>
    runAgentBrowser({ args, context, initScript, log, session })
  async function click(role, name) {
    // Vuetify teleports menus and dialogs, then animates them into place.
    // Keep ordinary hit-tested clicks, but wait briefly for their controls to
    // appear and become clickable after the opening transition.
    let lastError
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
            role === 'combobox' ? '.account-selection .v-field' : `@${ref}`,
          ])
          return
        } catch (error) {
          if (!String(error.message).includes('is covered by')) throw error
          lastError = error
        }
      } else {
        lastError = new Error(
          `Missing ${role} ${name}: ${JSON.stringify(snapshot)}`
        )
      }
      await run(['wait', '100'])
    }
    assert.fail(lastError?.message ?? `Could not click ${role} ${name}`)
  }
  const probe = async () =>
    (
      await run([
        'eval',
        `({ label: document.querySelector('.account-selection .v-select__selection-text')?.textContent, disabled: !!document.querySelector('.account-selection input')?.disabled, text: document.body.innerText, dialog: !!document.querySelector('.v-dialog.v-overlay--active'), busy: document.querySelector('[data-testid="route-content"] [aria-busy="true"]') !== null, loading: !!document.querySelector('[data-testid="route-content"] .v-skeleton-loader'), inert: !!document.querySelector('[data-testid="route-content"] [inert]') })`,
      ])
    ).result
  const before = await probe()
  assert.match(before.label, /Long synthetic investment/)
  await click('combobox', 'Account or Account group')
  await click('option', 'Second synthetic account')
  assert.equal(fixtureServer.pendingMutation, true)
  const during = await probe()
  assert.equal(during.label, before.label)
  assert.equal(during.disabled, true)
  assert.equal(during.busy, true)
  assert.ok(
    before.text.includes('100.00'),
    'Confirmed result must be loaded before the transition'
  )
  assert.equal(
    during.loading,
    true,
    'R6 deliberately invalidates old-context results while saving'
  )
  assert.equal(
    during.inert,
    true,
    'Pending route content must not accept actions'
  )
  assert.ok(
    during.text.includes('Updating to Second synthetic account'),
    'Pending choice must be distinct from the confirmed label'
  )
  fixtureServer.releaseMutation()
  await run(['wait', '300'])
  const failed = await probe()
  assert.equal(failed.label, before.label)
  assert.ok(failed.text.includes('Synthetic account denied'))
  await click('button', 'Display preferences')
  await click('button', 'Update')
  assert.equal(fixtureServer.pendingMutation, true)
  const saving = await probe()
  assert.equal(saving.dialog, true)
  assert.equal(saving.label, before.label)
  fixtureServer.releaseMutation()
  await run(['wait', '300'])
  const settingsFailed = await probe()
  assert.equal(settingsFailed.dialog, true)
  assert.ok(settingsFailed.text.includes('Synthetic settings denied'))
  assert.equal(settingsFailed.label, before.label)
  await click('button', 'Close')
  await log({
    context,
    before,
    during,
    failed,
    saving,
    settingsFailed,
    status: 'passed',
  })
}
