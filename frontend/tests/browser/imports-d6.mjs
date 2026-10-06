// D6 browser case: rendered protocol acceptance for the transaction import
// workflow over synthetic loopback WebSocket conversations. Every start,
// decision and stop rides the real transport against genuine backend
// envelopes (tests/browser/imports-ws.mjs); commands are asserted verbatim
// at the fixture server, exactly once per run.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const capturesDir = resolve(here, '../../../docs/design/assets/imports')

const evalProbe = async (run, expression) => (await run(['eval', expression])).result
const waitFor = (run, fn, timeout = 15000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const hasText = (text) =>
  `document.body.innerText.includes(${JSON.stringify(text)})`
const lacksText = (text) =>
  `!document.body.innerText.includes(${JSON.stringify(text)})`

const clickButtonByText = async (run, text, context) => {
  const clicked = await evalProbe(
    run,
    `(() => {
      const el = [...document.querySelectorAll('button')]
        .filter((b) => !b.disabled)
        .find((b) => b.textContent.trim() === ${JSON.stringify(text)})
      if (!el) return false
      el.scrollIntoView({ block: 'center' })
      el.click()
      return true
    })()`
  )
  assert.equal(clicked, true, `${context}: button ${JSON.stringify(text)} clickable`)
  await run(['wait', '200'])
}

const clickCardByText = async (run, text, context) => {
  const clicked = await evalProbe(
    run,
    `(() => {
      const el = [...document.querySelectorAll('.import-method-card')]
        .find((c) => c.textContent.includes(${JSON.stringify(text)}))
      if (!el) return false
      el.scrollIntoView({ block: 'center' })
      el.click()
      return true
    })()`
  )
  assert.equal(clicked, true, `${context}: method card ${text} clickable`)
  await run(['wait', '250'])
}

const chooseSelectOption = async (run, { label, option, context }) => {
  const opened = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')]
          .some((l) => l.textContent.trim() === ${JSON.stringify(label)}))
      if (!field) return false
      field.scrollIntoView({ block: 'center' })
      const target = field.querySelector('input') ?? field.querySelector('.v-field') ?? field
      target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
      target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      return true
    })()`
  )
  assert.equal(opened, true, `${context}: select ${label} opened`)
  await run(['wait', '700'])
  const chosen = await evalProbe(
    run,
    `(() => {
      const options = [
        ...document.querySelectorAll('.v-overlay .v-list-item'),
        ...document.querySelectorAll('[role="option"]'),
      ]
      const option = options.find((o) => o.textContent.includes(${JSON.stringify(option)}))
      if (!option) return false
      option.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
      option.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      return true
    })()`
  )
  assert.equal(chosen, true, `${context}: option ${option} chosen`)
  await run(['wait', '300'])
}

const setSyntheticFile = async (run, context) => {
  const result = await evalProbe(
    run,
    `(() => {
      const input = document.querySelector('.v-file-input input[type="file"]')
      if (!input) return { ok: false }
      const file = new File(['synthetic,csv,content'], 'synthetic-import.csv', { type: 'text/csv' })
      const transfer = new DataTransfer()
      transfer.items.add(file)
      input.files = transfer.files
      input.dispatchEvent(new Event('change', { bubbles: true }))
      return { ok: true, name: input.files[0]?.name ?? null }
    })()`
  )
  assert.equal(result.ok, true, `${context}: synthetic file attached`)
  assert.equal(result.name, 'synthetic-import.csv', `${context}: file name set`)
}

const capture = async (run, name) => {
  await mkdir(capturesDir, { recursive: true })
  const path = resolve(capturesDir, `d6-${name}.png`)
  await run(['screenshot', path])
  return path
}

const openImportDialog = async (run, context) => {
  const clicked = await evalProbe(
    run,
    `(() => {
      const el = document.querySelector('button[data-action="import-transactions"]')
      if (!el || el.disabled) return false
      el.scrollIntoView({ block: 'center' })
      el.click()
      return true
    })()`
  )
  assert.equal(clicked, true, `${context}: import action reachable`)
  await waitFor(run, hasText('Direct Import'))
  await run(['wait', '400'])
}

const backToMethodChoice = async (run, context) => {
  await clickButtonByText(run, 'Close', `${context} close outcome dialog`)
  // Parity with the incumbent: closing the success outcome keeps every
  // dialog closed; the next scenario reopens via the import action.
  await run(['wait', '400'])
}

const assertExactCommands = (importsWs, expected, context) => {
  assert.deepEqual(
    importsWs.state.commands,
    expected,
    `${context}: exact command sequence`
  )
}

const runFileFlowWithWarningResult = async ({ run, importsWs, context }) => {
  await openImportDialog(run, context)
  await clickCardByText(run, 'File Import', context)
  await clickButtonByText(run, 'Continue', context)
  await waitFor(run, hasText('Select Excel or CSV file to import'))

  await setSyntheticFile(run, context)
  await clickButtonByText(run, 'Analyze File', context)
  await waitFor(run, hasText('was automatically identified'))
  await waitFor(run, hasText('Select Account'))

  // Configuration capture: analyzed review state with the account choice.
  await capture(run, 'configuration-review')

  await clickButtonByText(run, 'Import Transactions', context)
  await waitFor(run, hasText('Import Progress'))
  assert.equal(importsWs.state.commands.length, 1, `${context}: one start sent`)
  assert.deepEqual(importsWs.state.commands[0], {
    type: 'start_file_import',
    file_id: 'synthetic-file-1',
    account_id: 3,
    confirm_every: false,
    is_galaxy: false,
    galaxy_type: null,
    currency: null,
  })

  await waitFor(run, hasText('Confirm Transaction'))
  await capture(run, 'decision-transaction-confirmation')

  await clickButtonByText(run, 'Confirm', context)
  await waitFor(run, hasText('Import Completed'))
  await waitFor(run, hasText('Some data sources could not be fetched'))
  const summary = await evalProbe(
    run,
    `(() => {
      const text = document.body.innerText
      return {
        total: text.includes('Total transactions processed'),
        imported: text.includes('Successfully imported'),
        duplicates: text.includes('Duplicates found'),
        skipped: text.includes('Skipped transactions'),
        errors: text.includes('Import Errors'),
        endpoint: text.includes('spot_fills'),
        endpointError: text.includes('OKX HTTP 500: synthetic endpoint failure'),
      }
    })()`
  )
  assert.deepEqual(
    summary,
    {
      total: true,
      imported: true,
      duplicates: true,
      skipped: true,
      errors: true,
      endpoint: true,
      endpointError: true,
    },
    `${context}: warning result renders all counters and the structured warning`
  )

  // Warning-result capture before closing.
  await capture(run, 'warning-result')

  assertExactCommands(
    importsWs,
    [
      {
        type: 'start_file_import',
        file_id: 'synthetic-file-1',
        account_id: 3,
        confirm_every: false,
        is_galaxy: false,
        galaxy_type: null,
        currency: null,
      },
      { type: 'transaction_confirmed', confirmed: true },
    ],
    context
  )

  await backToMethodChoice(run, context)
}

const runApiFlowWithMatchingAndMapping = async ({ run, importsWs, context }) => {
  await openImportDialog(run, context)
  await clickCardByText(run, 'Direct Import', context)
  await clickButtonByText(run, 'Continue', context)
  await waitFor(run, hasText('Select Broker Account'))

  await chooseSelectOption(run, {
    label: 'Select Broker Account',
    option: 'Tinkoff',
    context,
  })
  await clickButtonByText(run, 'Import Transactions', context)
  await waitFor(run, hasText('Match Accounts for Tinkoff'))

  assert.deepEqual(importsWs.state.commands.at(-1), {
    type: 'start_api_import',
    data: {
      broker_id: 11,
      confirm_every_transaction: false,
      date_from: null,
      date_to: null,
    },
  })

  await clickButtonByText(run, 'Continue with existing matches only', context)
  await waitFor(run, hasText('Map Security'))
  // The mapping autocomplete preselects the best match (match_id 31).
  await waitFor(run, hasText('Best match found'))
  await capture(run, 'decision-security-mapping')

  await clickButtonByText(run, 'Map and Confirm', context)
  await waitFor(run, hasText('Import Completed'))

  assertExactCommands(
    importsWs,
    [
      {
        type: 'start_file_import',
        file_id: 'synthetic-file-1',
        account_id: 3,
        confirm_every: false,
        is_galaxy: false,
        galaxy_type: null,
        currency: null,
      },
      { type: 'transaction_confirmed', confirmed: true },
      {
        type: 'start_api_import',
        data: {
          broker_id: 11,
          confirm_every_transaction: false,
          date_from: null,
          date_to: null,
        },
      },
      { type: 'use_existing_matches', data: { pairs: [
        {
          tinkoff_account_id: '222444555',
          db_account_id: 7,
          tinkoff_account: {
            id: '222444555',
            name: 'T-Invest Brokerage',
            type: 'BROKERAGE',
          },
          db_account: { id: 7, name: 'Tinkoff Main', broker: 2 },
        },
      ] } },
      { type: 'security_mapped', action: 'map', security_id: 31 },
    ],
    context
  )

  await backToMethodChoice(run, context)
}

const runStopFlowWithDelayedAck = async ({ run, importsWs, context }) => {
  await openImportDialog(run, context)
  await clickCardByText(run, 'File Import', context)
  await clickButtonByText(run, 'Continue', context)
  await setSyntheticFile(run, context)
  await clickButtonByText(run, 'Analyze File', context)
  await waitFor(run, hasText('was automatically identified'))
  await clickButtonByText(run, 'Import Transactions', context)
  await waitFor(run, hasText('Import Progress'))

  await clickButtonByText(run, 'Stop Import', context)
  // Stopping persists: the stop control disables and no outcome appears
  // until the actual import_stopped acknowledgment arrives.
  await run(['wait', '600'])
  const stopping = await evalProbe(
    run,
    `(() => {
      const stop = [...document.querySelectorAll('button')]
        .find((b) => b.textContent.trim() === 'Stop Import')
      return {
        stopDisabled: stop ? stop.disabled : null,
        outcomeShown: document.body.innerText.includes('Import process was stopped by user'),
      }
    })()`
  )
  assert.equal(stopping.stopDisabled, true, `${context}: stop control disabled while stopping`)
  assert.equal(stopping.outcomeShown, false, `${context}: no premature stopped outcome`)
  assert.deepEqual(
    importsWs.state.commands.at(-1),
    { type: 'stop_import' },
    `${context}: stop sent once`
  )
  assert.equal(
    importsWs.state.commands.filter((c) => c.type === 'stop_import').length,
    1,
    `${context}: exactly one stop command`
  )

  await capture(run, 'stopping')

  const answered = importsWs.answerStop()
  assert.equal(answered, true, `${context}: delayed acknowledgment delivered`)
  await waitFor(run, hasText('Import process was stopped by user'))
  assert.equal(
    await evalProbe(run, lacksText('Import Completed')),
    true,
    `${context}: stop never claims completion`
  )
  // Dismissing the stopped outcome returns to a clean method choice.
  await clickButtonByText(run, 'Close', `${context} close stopped outcome`)
  await run(['wait', '400'])
}

const runFailedConnectFlow = async ({ run, importsWs, context }) => {
  importsWs.sever()
  await openImportDialog(run, context)
  await clickCardByText(run, 'File Import', context)
  await clickButtonByText(run, 'Continue', context)
  await setSyntheticFile(run, context)
  await clickButtonByText(run, 'Analyze File', context)
  await waitFor(run, hasText('was automatically identified'))

  await clickButtonByText(run, 'Import Transactions', context)
  await waitFor(run, hasText('WebSocket not connected. Please try again.'))
  assert.equal(
    await evalProbe(run, lacksText('Import Progress')),
    true,
    `${context}: failed connect never shows a running import`
  )
  assert.equal(
    await evalProbe(run, lacksText('Import Completed')),
    true,
    `${context}: failed connect never claims completion`
  )
  assert.equal(
    importsWs.state.commands.filter((c) => c.type === 'start_file_import').length,
    2,
    `${context}: no duplicate start beyond the failed attempt`
  )
  await clickButtonByText(run, 'Close', `${context} close failed-connect error`)
  // A recoverable error dismisses back into configuration with the inputs
  // retained for a retry. (Button labels render uppercased, so wait on the
  // untouched file-input label.)
  await waitFor(run, hasText('Select Excel or CSV file to import'))
  await run(['wait', '300'])
}

const runStaleEventFlow = async ({ run, importsWs, context }) => {
  // Ensure a clean method choice regardless of how the previous scenario
  // ended: Cancel resets the whole workflow (inputs cleared).
  await evalProbe(
    run,
    `(() => {
      const cancel = [...document.querySelectorAll('button')]
        .find((b) => b.textContent.trim() === 'Cancel')
      if (cancel) {
        cancel.click()
        return true
      }
      return false
    })()`
  )
  await run(['wait', '400'])
  await openImportDialog(run, context)
  const before = importsWs.state.commands.length
  importsWs.queueLate({
    type: 'import_complete',
    data: {
      totalTransactions: 99,
      importedTransactions: 99,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0,
      warnings: [],
    },
    message: 'Import process completed',
  })
  assert.equal(importsWs.flushLate(), 1, `${context}: stale event flushed`)
  await run(['wait', '600'])
  assert.equal(
    await evalProbe(run, lacksText('Import Completed')),
    true,
    `${context}: stale completion never renders`
  )
  assert.equal(
    await evalProbe(run, hasText('Direct Import')),
    true,
    `${context}: workflow stays at the method choice`
  )
  assert.equal(
    importsWs.state.commands.length,
    before,
    `${context}: stale events send nothing`
  )

  // Close/reopen keeps no previous file: the analyze action stays disabled
  // until a new file is attached.
  await clickCardByText(run, 'File Import', context)
  await clickButtonByText(run, 'Continue', context)
  const fileState = await evalProbe(
    run,
    `(() => {
      const analyze = [...document.querySelectorAll('button')]
        .find((b) => b.textContent.trim() === 'Analyze File')
      const input = document.querySelector('.v-file-input input[type="file"]')
      return { analyzeDisabled: analyze ? analyze.disabled : null, files: input ? input.files.length : null }
    })()`
  )
  assert.equal(fileState.files, 0, `${context}: previous file cleared on close/reopen`)
  assert.equal(fileState.analyzeDisabled, true, `${context}: analyze disabled without a file`)

  // Leave the workflow at the method choice for the next scenario.
  await clickButtonByText(run, 'Back', context)
  await waitFor(run, hasText('Direct Import'))
  await run(['wait', '250'])
}

const runZoomProbe = async ({ appOrigin, context, initScript, log, session }) => {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const cdpInfo = await runAgentBrowser({ args: ['get', 'cdp-url'], context: `${context} cdp`, initScript, log, session })
  const cdpUrl = cdpInfo.cdpUrl ?? (cdpInfo.result && cdpInfo.result.cdpUrl)
  assert.ok(cdpUrl, `${context}: cdp url available`)
  const zoomTo = (percent) =>
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

  await run(['open', `${appOrigin}/transactions`])
  await waitFor(run, `document.querySelector('button[data-action="import-transactions"]') !== null`)
  const zoomed = await zoomTo(200)
  assert.equal(zoomed.code, 0, `${context}: native 200% zoom verified (${zoomed.out.trim()})`)
  await run(['wait', '300'])
  await openImportDialog(run, `${context} zoom`)
  const probe = await evalProbe(
    run,
    `(() => {
      const within = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
      const hit = (el) => { const b = el.getBoundingClientRect(); const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!h && (el.contains(h) || h === el) }
      const cards = [...document.querySelectorAll('.import-method-card')]
      return {
        dpr: window.devicePixelRatio,
        cards: cards.length,
        contained: cards.every(within),
        hittable: cards.every((el) => { el.scrollIntoView({ block: 'center' }); return hit(el) }),
      }
    })()`
  )
  assert.ok(probe.dpr >= 1.9, `${context}: devicePixelRatio is real browser zoom (${probe.dpr})`)
  assert.equal(probe.cards, 2, `${context}: both method cards render at 200%`)
  assert.equal(probe.contained, true, `${context}: method cards within viewport at 200%`)
  assert.equal(probe.hittable, true, `${context}: method cards hittable at 200%`)
  await capture(run, 'zoom200-method-choice')
  const reset = await zoomTo(100)
  assert.equal(reset.code, 0, `${context}: zoom reset verified (${reset.out.trim()})`)
}

export async function assertImportsD6Flow({ appOrigin, context, initScript, log, session, fixtureServer, viewport }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const importsWs = fixtureServer.importsWs

  if (viewport.name !== 'desktop') {
    // Mobile layout probe: the configuration surface stays contained and
    // hittable at 390px.
    await run(['open', `${appOrigin}/transactions`])
    await waitFor(run, `document.querySelector('button[data-action="import-transactions"]') !== null`)
    await openImportDialog(run, context)
    const probe = await evalProbe(
      run,
      `(() => {
        const within = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
        const hit = (el) => { const b = el.getBoundingClientRect(); const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!h && (el.contains(h) || h === el) }
        const cards = [...document.querySelectorAll('.import-method-card')]
        const reach = (el) => { el.scrollIntoView({ block: 'center' }); return within(el) && hit(el) }
        return {
          viewport: innerWidth,
          cards: cards.length,
          contained: cards.every(within),
          hittable: cards.every(reach),
          cancel: [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Cancel' && reach(b)),
        }
      })()`
    )
    assert.equal(probe.viewport, 390, `${context}: mobile viewport applied`)
    assert.equal(probe.cards, 2, `${context}: method cards render on mobile`)
    assert.equal(probe.contained, true, `${context}: method cards within 390px viewport`)
    assert.equal(probe.hittable, true, `${context}: method cards hittable on mobile`)
    assert.equal(probe.cancel, true, `${context}: cancel reachable on mobile`)
    await capture(run, 'mobile-configuration')
    return
  }

  await run(['open', `${appOrigin}/transactions`])
  await waitFor(run, `document.querySelector('button[data-action="import-transactions"]') !== null`)

  // Stale-event containment on the idle-connected socket, before any run.
  await runStaleEventFlow({ run, importsWs, context: `${context} stale-events` })

  const tableRequestsBefore = fixtureServer.requests.filter(
    (request) => request.path === '/transactions/api/get_transactions_table/'
  ).length

  await runFileFlowWithWarningResult({ run, importsWs, context: `${context} file-flow` })

  // Parent invalidation: the transactions page refetched its table after
  // the accepted completion (import-completed → handleImportCompleted).
  const tableRequestsAfter = fixtureServer.requests.filter(
    (request) => request.path === '/transactions/api/get_transactions_table/'
  ).length
  assert.ok(
    tableRequestsAfter > tableRequestsBefore,
    `${context}: parent refetched transactions after completion`
  )

  await runApiFlowWithMatchingAndMapping({ run, importsWs, context: `${context} api-flow` })
  await runStopFlowWithDelayedAck({ run, importsWs, context: `${context} stop-flow` })
  await runFailedConnectFlow({ run, importsWs, context: `${context} failed-connect` })
  await runStaleEventFlow({ run, importsWs, context: `${context} stale-events-late` })
  await runZoomProbe({ appOrigin, context: `${context} zoom`, initScript, log, session })

  console.log(`PASS ${context} imports-d6 rendered protocol acceptance`)
}
