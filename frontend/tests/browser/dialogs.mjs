import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

const flows = {
  // D4 action hierarchy: primary/secondary stay buttons; the rest sit in
  // the overflow menu behind 'More actions'. D5 moved the prices-page
  // 'Add Security' into that overflow as well.
  '/transactions': ['Add transaction', 'Import transactions', 'Add FX transaction', 'Transfer asset', 'Record merger'],
  '/database/accounts': ['Add Account'],
  '/database/brokers': ['Add Broker'],
  '/database/securities': ['Add Security', 'Record Merger'],
  '/database/prices': ['Add Price Entry', 'Add Security', 'Import Prices'],
  '/database/fx': ['Add FX Rate', 'Import FX Rates'],
  '/dashboard': ['Update Account Performance'],
}

export const dialogRoutes = Object.keys(flows)

export async function assertDialogChunkRecovery({ context, initScript, log, session }) {
  const run = args => runAgentBrowser({ args, context, initScript, log, session })
  // C4 recorded a race where a click landed while a Vuetify overlay scrim was
  // still in its leave transition and covered the click point. The bounded
  // synchronization retries a refused covered click (the same accepted
  // pattern as the dialogs flow below); a missing control still fails the
  // case, and every assertion stays.
  async function click(name) {
    let lastError = null
    for (let attempt = 0; attempt < 12; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const ref = Object.entries(snapshot.refs).find(([, item]) => item.role === 'button' && item.name.toLowerCase() === name.toLowerCase())?.[0]
      if (ref) {
        try { await run(['click', `@${ref}`]); return }
        catch (error) { if (!error.message.includes('is covered by')) throw error; lastError = error }
      } else {
        lastError = new Error(`Missing ${name}`)
      }
      await run(['wait', '100'])
    }
    throw lastError ?? new Error(`Missing ${name}`)
  }
  await click('Import Transactions')
  await run(['wait', '--fn', `document.querySelector('[data-testid="route-load-error"]') !== null`])
  await click('Reload application')
  await run(['wait', '--fn', `location.pathname === '/transactions' && document.querySelector('[data-testid="route-load-error"]') === null && document.body.innerText.includes('IMPORT TRANSACTIONS')`])
  await click('Import Transactions')
  await run(['wait', '--fn', `document.querySelector('.v-dialog.v-overlay--active')?.innerText.includes('Import Transactions')`])
  const errors = await run(['errors'])
  assert.deepEqual(errors.errors, [], 'Handled dialog import failure must not leave unhandled page errors')
  await log({ context, status: 'failed import visibly recovered by explicit reload' })
}

export async function assertDialogDeliveryFlow({ context, initScript, log, session, route }) {
  const run = args => runAgentBrowser({ args, context, initScript, log, session })
  async function clickButton(names) {
    let lastError
    for (let attempt = 0; attempt < 12; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const ref = Object.entries(snapshot.refs).find(([, item]) => item.role === 'button' && names.some(name => item.name.toLowerCase() === name.toLowerCase()))?.[0]
      if (ref) {
        try { await run(['click', `@${ref}`]); return }
        catch (error) { if (!error.message.includes('is covered by')) throw error; lastError = error }
      } else lastError = new Error(`Missing button ${names}: ${JSON.stringify(snapshot)}`)
      await run(['wait', '100'])
    }
    throw lastError
  }
  const defaultOverflowActions = new Set(['Add FX transaction', 'Transfer asset', 'Record merger'])
  // 'Add Security' sits in the overflow only on the prices page (D5); on the
  // securities inventory it stays a visible secondary action.
  const isOverflowAction = (name) =>
    name === 'Add Security' ? route.path === '/database/prices' : defaultOverflowActions.has(name)
  const openOverflow = async () => {
    for (let attempt = 0; attempt < 8; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const more = Object.entries(snapshot.refs).find(([, item]) => item.role === 'button' && item.name === 'More actions')?.[0]
      if (more) {
        await run(['click', `@${more}`])
        await run(['wait', '--fn', `document.querySelectorAll('.v-overlay--active [data-action]').length >= 1`])
        return
      }
      await run(['wait', '100'])
    }
    throw new Error('Overflow More actions control missing')
  }
  const clickAction = async (name) => {
    if (isOverflowAction(name)) {
      await openOverflow()
      await run(['eval', `(() => { const item = [...document.querySelectorAll('.v-overlay--active [data-action]')].find(el => el.textContent.trim().startsWith('${name}')); if (!item) throw new Error('overflow item ${name} missing'); item.click(); return true })()`])
      return
    }
    await clickButton([name])
  }
  for (const button of flows[route.path]) {
    const closeDialog = () => button === 'Import Prices' ? run(['press', 'Escape']) : clickButton(['Cancel', 'Close'])
    await clickAction(button)
    await run(['wait', '--fn', `document.querySelector('.v-dialog.v-overlay--active .v-card') !== null`])
    const result = await run(['eval', `({ text: document.querySelector('.v-dialog.v-overlay--active')?.innerText, icons: document.querySelectorAll('.v-dialog.v-overlay--active svg path').length })`])
    assert.ok(result.result.text.length > 0, `${button}: missing dialog content`)
    await closeDialog()
    await run(['wait', '--fn', `document.querySelector('.v-dialog.v-overlay--active') === null`])
    // Reopening exercises a retained first-use component without remounting
    // it. Overflow-hosted actions must reopen through the same overflow
    // path (the D4-era reopen called clickButton directly, which can never
    // find a menu-hosted action — repaired with the D5 prices overflow).
    await clickAction(button)
    await run(['wait', '--fn', `document.querySelector('.v-dialog.v-overlay--active .v-card') !== null`])
    await closeDialog()
    await run(['wait', '--fn', `document.querySelector('.v-dialog.v-overlay--active') === null`])
    await log({ context, dialog: button, status: 'opened, closed and reopened' })
  }
  const errors = await run(['errors'])
  assert.deepEqual(errors.errors, [], `${context}: dialog page errors`)
  const messages = await run(['console'])
  assert.equal(/Failed to resolve component|Failed to resolve directive|Unknown icon:/.test(JSON.stringify(messages)), false, `${context}: unresolved UI registration`)
}
