import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

const flows = {
  // D4 action hierarchy: primary/secondary stay buttons; the rest sit in
  // the overflow menu behind 'More actions'.
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
  async function click(name) {
    const snapshot = await run(['snapshot', '-i'])
    const ref = Object.entries(snapshot.refs).find(([, item]) => item.role === 'button' && item.name.toLowerCase() === name.toLowerCase())?.[0]
    assert.ok(ref, `Missing ${name}`)
    await run(['click', `@${ref}`])
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
  const overflowActions = new Set(['Add FX transaction', 'Transfer asset', 'Record merger'])
  const openOverflow = async () => {
    for (let attempt = 0; attempt < 8; attempt++) {
      const snapshot = await run(['snapshot', '-i'])
      const more = Object.entries(snapshot.refs).find(([, item]) => item.role === 'button' && item.name === 'More actions')?.[0]
      if (more) {
        await run(['click', `@${more}`])
        await run(['wait', '--fn', `document.querySelectorAll('.v-overlay--active [data-action]').length >= 3`])
        return
      }
      await run(['wait', '100'])
    }
    throw new Error('Overflow More actions control missing')
  }
  const clickAction = async (name) => {
    if (overflowActions.has(name)) {
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
    // Reopening exercises a retained first-use component without remounting it.
    await clickButton([button])
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
