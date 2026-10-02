import assert from 'node:assert/strict'
import { runAgentBrowser } from './protocol.mjs'

/** Real inputs replace a pending query; held old responses finish last. */
export async function assertRequestOrderFlow({ context, initScript, log, session, fixtureServer, route }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const path = route.path === '/database/fx' ? '/database/api/fx/list_fx/' : '/transactions/api/get_transactions_table/'
  // D4 gave each route's toolbar search its own accessible name; both remain
  // exact-label matches, never an arbitrary first textbox.
  const searchName = route.path === '/database/fx' ? 'Search' : 'Search transactions'
  const findSearchRef = (snapshot) => Object.entries(snapshot.refs).find(([, item]) => item.role === 'textbox' && item.name === searchName)?.[0]
  const snapshot = await run(['snapshot', '-i'])
  const searchRef = findSearchRef(snapshot)
  assert.ok(searchRef, `${searchName} must be accessible through its label`)
  await run(['fill', `@${searchRef}`, 'GBP'])
  for (let attempt = 0; !fixtureServer.heldReads.has(path) && attempt < 15; attempt++) await run(['wait', '100'])
  assert.ok(fixtureServer.heldReads.has(path), 'old search request must still be pending')
  const nextSnapshot = await run(['snapshot', '-i'])
  const nextRef = findSearchRef(nextSnapshot)
  assert.ok(nextRef)
  await run(['fill', `@${nextRef}`, 'EUR'])
  for (let attempt = 0; !fixtureServer.requests.some((item) => item.path === path && item.body?.search === 'EUR' && item.completed) && attempt < 15; attempt++) await run(['wait', '100'])
  const newer = fixtureServer.requests.filter((item) => item.path === path && item.body?.search === 'EUR' && item.completed)
  assert.equal(newer.length, 1, 'new filters must run while the old query is unresolved')
  await run(['wait', '200'])
  const before = (await run(['eval', `({ text: document.querySelector('.v-data-table')?.innerText, path: location.pathname })`])).result
  assert.ok(before.text.includes('EUR'), 'new currency rows/headers must be rendered')
  assert.ok(!before.text.includes('GBP'), 'old data must not render')
  fixtureServer.releaseRead(path)
  await run(['wait', '250'])
  const after = (await run(['eval', `({ text: document.querySelector('.v-data-table')?.innerText, path: location.pathname })`])).result
  assert.equal(after.path, route.path)
  assert.equal(after.text, before.text, 'late old response must not alter the current table')
  await log({ context, route: route.path, newer: newer.length, before, after, status: 'passed' })
}
