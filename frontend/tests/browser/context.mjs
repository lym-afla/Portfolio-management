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
    const snapshot = await run(['snapshot', '-i'])
    const ref = Object.entries(snapshot.refs).find(
      ([, item]) =>
        item.role === role && item.name.toLowerCase() === name.toLowerCase()
    )?.[0]
    assert.ok(ref, `Missing ${role} ${name}: ${JSON.stringify(snapshot)}`)
    if (role === 'combobox') {
      await run(['focus', `@${ref}`])
      await run(['press', 'Enter'])
    } else await run(['click', `@${ref}`])
  }
  const probe = async () =>
    (
      await run([
        'eval',
        `({ label: document.querySelector('.account-selection .v-select__selection-text')?.textContent, disabled: !!document.querySelector('.account-selection input')?.disabled, text: document.body.innerText, dialog: !!document.querySelector('.v-dialog.v-overlay--active'), busy: document.querySelector('[aria-busy="true"]') !== null })`,
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
    during.text.includes('100.00'),
    'Prior confirmed portfolio result should remain visible'
  )
  fixtureServer.releaseMutation()
  await run(['wait', '300'])
  const failed = await probe()
  assert.equal(failed.label, before.label)
  assert.ok(failed.text.includes('Synthetic account denied'))
  await click('button', 'Portfolio settings')
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
