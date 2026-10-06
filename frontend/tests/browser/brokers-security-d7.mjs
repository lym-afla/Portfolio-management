// D7 browser case: rendered acceptance for the extracted broker connection
// surface (/profile/settings) and security detail sections
// (/database/securities/:id) over backend-faithful synthetic loopback
// fixtures. Exact identities/payloads are asserted at the fixture server,
// credentials stay masked in captures (password inputs only), and every
// control is verified by bounds AND elementFromPoint hit-testing below the
// fixed header. Native 200% zoom rides the CDP zoom script with DPR
// verification and reset.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runAgentBrowser } from './protocol.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const capturesDir = resolve(here, '../../../docs/design/assets/brokers-security')

const evalProbe = async (run, expression) => (await run(['eval', expression])).result
const waitFor = (run, fn, timeout = 15000) =>
  run(['wait', '--fn', fn, '--timeout', String(timeout)])

const hasText = (text) =>
  `document.body.innerText.includes(${JSON.stringify(text)})`
const lacksText = (text) =>
  `!document.body.innerText.includes(${JSON.stringify(text)})`

const capture = async (run, name) => {
  await mkdir(capturesDir, { recursive: true })
  const path = resolve(capturesDir, `d7-${name}.png`)
  await run(['screenshot', path])
  return path
}

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
  await run(['wait', '250'])
}

const clickIconButton = async (run, ariaLabel, context, { which = 'first' } = {}) => {
  const clicked = await evalProbe(
    run,
    `(() => {
      const el = [...document.querySelectorAll('button')]
        .filter((b) => !b.disabled && b.getAttribute('aria-label') === ${JSON.stringify(ariaLabel)})
        .at(${which === 'first' ? '0' : '-1'})
      if (!el) return false
      el.scrollIntoView({ block: 'center' })
      el.click()
      return true
    })()`
  )
  assert.equal(clicked, true, `${context}: icon button ${ariaLabel} clickable`)
  await run(['wait', '300'])
}

const fillTextField = async (run, label, value, context) => {
  const filled = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === ${JSON.stringify(label)}))
      if (!field) return false
      const input = field.querySelector('input')
      if (!input) return false
      input.value = ${JSON.stringify(value)}
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      return true
    })()`
  )
  assert.equal(filled, true, `${context}: field ${label} filled`)
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
  await run(['wait', '400'])
}

// Bounds + elementFromPoint hit-test below the fixed header, for every
// selector the caller cares about. Reports per-selector diagnostics.
const assertFlowVisible = async (run, selectors, context, { minCount = {} } = {}) => {
  const probe = await evalProbe(
    run,
    `(() => {
      const headerBottom = Math.max(0, ...[...document.querySelectorAll('.v-toolbar, .v-app-bar')]
        .filter((el) => { const s = getComputedStyle(el); return (s.position === 'fixed' || s.position === 'sticky') })
        .map((el) => el.getBoundingClientRect().bottom))
      const selectors = ${JSON.stringify(selectors)}
      const minimums = ${JSON.stringify(minCount)}
      const within = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
      const belowHeader = (el) => el.getBoundingClientRect().bottom > headerBottom - 1 || el.scrollHeight === 0
      const hit = (el) => {
        const b = el.getBoundingClientRect()
        const h = document.elementFromPoint(b.left + b.width / 2, Math.min(Math.max(b.top + b.height / 2, headerBottom + 1), innerHeight - 1))
        return !!h && (el.contains(h) || h === el)
      }
      const report = {}
      let ok = true
      for (const selector of selectors) {
        const els = [...document.querySelectorAll(selector)].filter((el) => {
          const b = el.getBoundingClientRect()
          return b.width > 0 && b.height > 0
        })
        const reachable = els.map((el) => {
          el.scrollIntoView({ block: 'center' })
          const b = el.getBoundingClientRect()
          return { within: within(el), hit: hit(el), rect: { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) } }
        })
        report[selector] = { count: els.length, allReachable: reachable.every((r) => r.within && r.hit) }
        if (!report[selector].allReachable) report[selector].details = reachable
        if (els.length < (minimums[selector] ?? 1) || !report[selector].allReachable) ok = false
      }
      return { headerBottom, ok, report }
    })()`
  )
  assert.equal(probe.ok, true, `${context}: controls visible and hittable: ${JSON.stringify(probe.report)}`)
  return probe
}

// The expansion panels are single-open (Vuetify default, incumbent parity):
// opening a provider panel closes the others, so the flow navigates to one
// provider at a time. Counts stay visible in the collapsed titles.
const waitForBrokerPanels = async (run) => {
  await waitFor(
    run,
    `document.querySelectorAll('.v-expansion-panel-title').length >= 4`
  )
  await run(['wait', '300'])
}

const openProviderPanel = async (run, panelName, context) => {
  const opened = await evalProbe(
    run,
    `(() => {
      const title = [...document.querySelectorAll('.v-expansion-panel-title')]
        .find((el) => el.textContent.includes(${JSON.stringify(panelName)}))
      if (!title) return { found: false }
      const wasOpen = title.getAttribute('aria-expanded') === 'true'
      if (!wasOpen) {
        title.scrollIntoView({ block: 'center' })
        title.click()
      }
      return { found: true, wasOpen }
    })()`
  )
  assert.equal(opened.found, true, `${context}: panel ${panelName} present`)
  if (!opened.wasOpen) await run(['wait', '400'])
  const state = await evalProbe(
    run,
    `(() => [...document.querySelectorAll('.v-expansion-panel-title')]
      .find((el) => el.textContent.includes(${JSON.stringify(panelName)}))
      ?.getAttribute('aria-expanded'))()`
  )
  assert.equal(state, 'true', `${context}: panel ${panelName} expanded`)
}

const initialTokens = () => ({
  tinkoff_tokens: [
    { id: 11, token_type: 'read_only', sandbox_mode: false, is_active: true, created_at: '2026-09-01T10:30:00Z' },
    { id: 12, token_type: 'full_access', sandbox_mode: false, is_active: false, created_at: '2026-08-01T09:00:00Z' },
  ],
  ib_tokens: [{ id: 1 }],
  bybit_tokens: [
    { id: 21, api_key: 'bybit-synthetic-key', testnet: true, is_active: true, created_at: '2026-07-15T08:00:00Z' },
  ],
  okx_tokens: [
    { id: 31, api_key: 'okx-synthetic-key', simulated_trading: true, is_active: false, created_at: '2026-06-02T12:00:00Z' },
  ],
})

export async function assertBrokersSecurityD7Flow({ appOrigin, context, initScript, log, session, fixtureServer, viewport }) {
  const run = (args) => runAgentBrowser({ args, context, initScript, log, session })
  const d7 = fixtureServer.brokersSecurityD7
  // Every pass starts from the same token inventory, so both desktop routes
  // exercise identical flows against identical state.
  d7.tokens = initialTokens()

  // ---------- Security detail sections (populated bond/crypto + probes) --
  const runSecurityFlows = async () => {
    // Stock page (manifest route): five resources, verbatim values.
    await run(['open', `${appOrigin}/database/securities/1`])
    await waitFor(run, hasText('Fixture Stock'))
    await run(['wait', '400'])
    let probe = await evalProbe(
      run,
      `(() => {
        const text = document.body.innerText
        return {
          heading: text.includes('Fixture Stock'),
          position: text.includes('10.000000000'),
          value: text.includes('$1,022.50'),
          charts: document.querySelectorAll('canvas').length,
          range: text.includes('Showing 1-10 of 23 entries'),
        }
      })()`
    )
    assert.deepEqual(
      probe,
      { heading: true, position: true, value: true, charts: 2, range: true },
      `${context}: stock page renders values and charts`,
    )
    const securityRequestsBefore = d7.securityRequests.length

    // Populated bond page: verbatim percentage + bond-only rows.
    await run(['open', `${appOrigin}/database/securities/2`])
    await waitFor(run, hasText('Fixture Bond'))
    await run(['wait', '400'])
    probe = await evalProbe(
      run,
      `(() => {
        const text = document.body.innerText
        return {
          title: document.querySelector('[data-testid="workspace-page-heading"]')?.textContent?.trim() ?? '',
          bondPrice: text.includes('99.125000%'),
          aci: text.includes('Total Accrued Interest:') && text.includes('25.00'),
          netOfAci: text.includes('(net of ACI paid at acquisition)'),
          amortizing: text.includes('Current Nominal:') && text.includes('Initial Nominal:') && text.includes('(Amortizing)'),
          coupon: text.includes('4.375000%') && text.includes('2x per year') && text.includes('90 / 181 days'),
          realized: text.includes('($17.50)'),
        }
      })()`
    )
    assert.equal(probe.title, 'Fixture Bond', `${context}: bond title`)
    assert.deepEqual(
      { ...probe, title: undefined },
      { bondPrice: true, aci: true, netOfAci: true, amortizing: true, coupon: true, realized: true, title: undefined },
      `${context}: bond page values`,
    )
    await capture(run, 'bond-desktop')

    // Period change: price+position+transactions refetch with the new
    // period; transactions page resets to 1; detail untouched.
    const counts = {
      price: d7.securityRequests.filter((r) => r.path.includes('price-history')).length,
      position: d7.securityRequests.filter((r) => r.path.includes('position-history')).length,
      transactions: d7.securityRequests.filter((r) => r.path.includes('/transactions')).length,
      detail: d7.securityRequests.filter((r) => /securities\/\d+\/$/.test(r.path)).length,
    }
    const clickedPeriod = await evalProbe(
      run,
      `(() => {
        const buttons = [...document.querySelectorAll('button')]
          .filter((b) => b.textContent.trim() === 'All' && b.closest('.v-btn-toggle, .v-btn-group, [class*="timeline"], .v-col, section, div'))
        const el = buttons.at(0)
        if (!el) return false
        el.scrollIntoView({ block: 'center' })
        el.click()
        return true
      })()`
    )
    assert.equal(clickedPeriod, true, `${context}: period All clickable`)
    await run(['wait', '500'])
    const afterPeriod = {
      price: d7.securityRequests.filter((r) => r.path.includes('price-history')).length,
      position: d7.securityRequests.filter((r) => r.path.includes('position-history')).length,
      transactions: d7.securityRequests.filter((r) => r.path.includes('/transactions')).length,
      detail: d7.securityRequests.filter((r) => /securities\/\d+\/$/.test(r.path)).length,
    }
    assert.equal(afterPeriod.price, counts.price + 1, `${context}: one price refetch`)
    assert.equal(afterPeriod.position, counts.position + 1, `${context}: one position refetch`)
    assert.equal(afterPeriod.transactions, counts.transactions + 1, `${context}: one transactions refetch`)
    assert.equal(afterPeriod.detail, counts.detail, `${context}: detail untouched`)
    assert.equal(
      d7.securityRequests.filter((r) => r.path.includes('price-history')).at(-1).query.period,
      'All',
      `${context}: price query carries the All period`,
    )
    assert.equal(
      d7.securityRequests.filter((r) => r.path.includes('/transactions')).at(-1).query.page,
      '1',
      `${context}: transactions page reset to 1`,
    )

    // Pagination: page 2 issues exactly one transactions request for page 2.
    const transactionsBeforePage = d7.securityRequests.filter((r) => r.path.includes('/transactions')).length
    const clickedPage2 = await evalProbe(
      run,
      `(() => {
        const btn = [...document.querySelectorAll('.v-pagination button')]
          .find((b) => b.textContent.trim() === '2' && !b.disabled)
        if (!btn) return false
        btn.scrollIntoView({ block: 'center' })
        btn.click()
        return true
      })()`
    )
    assert.equal(clickedPage2, true, `${context}: pagination page 2 clickable`)
    await run(['wait', '600'])
    assert.equal(
      d7.securityRequests.filter((r) => r.path.includes('/transactions')).length,
      transactionsBeforePage + 1,
      `${context}: exactly one transactions refetch for page 2`,
    )
    assert.equal(
      d7.securityRequests.filter((r) => r.path.includes('/transactions')).at(-1).query.page,
      '2',
      `${context}: transactions query carried page 2`,
    )

    // Account change: detail+price+position+transactions refetch with
    // account_id=7; the account-choices resource is NOT refetched.
    const recordCountBeforeAccount = d7.securityRequests.length
    await chooseSelectOption(run, { label: 'Broker Account', option: 'Main synthetic account', context })
    await run(['wait', '800'])
    const accountFieldText = await evalProbe(
      run,
      `(() => {
        const field = [...document.querySelectorAll('.v-input')]
          .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'Broker Account'))
        if (!field) return 'field-not-found'
        const input = field.querySelector('input')
        const selection = field.querySelector('.v-select__selection')
        return { inputValue: input ? input.value : null, selection: selection ? selection.textContent.trim() : null }
      })()`
    )
    console.log(`DIAG ${context} account field:`, JSON.stringify(accountFieldText))
    const accountRecords = d7.securityRequests.slice(recordCountBeforeAccount)
    assert.equal(accountRecords.length, 4, `${context}: exactly four refetches on account change (${JSON.stringify(accountRecords.map((r) => r.path))})`)
    assert.ok(
      accountRecords.some((r) => /securities\/\d+\/$/.test(r.path)) &&
        accountRecords.some((r) => r.path.includes('price-history')) &&
        accountRecords.some((r) => r.path.includes('position-history')) &&
        accountRecords.some((r) => r.path.includes('/transactions')),
      `${context}: detail, price, position and transactions all refetched`,
    )
    // Characterized signatures: price history takes no account parameter;
    // detail, position and transactions carry account_id=7.
    for (const record of accountRecords) {
      if (record.path.includes('price-history')) {
        assert.equal(
          record.query.account_id,
          undefined,
          `${context}: price query stays account-free (${JSON.stringify(record.query)})`,
        )
      } else {
        assert.equal(
          record.query.account_id,
          '7',
          `${context}: ${record.path} carried ${JSON.stringify(record.query)}`,
        )
      }
    }

    // Crypto page: beyond-safe-integer quantity verbatim plus the
    // characterized empty activity state.
    await run(['open', `${appOrigin}/database/securities/3`])
    await waitFor(run, hasText('Fixture Coin'))
    await run(['wait', '400'])
    probe = await evalProbe(
      run,
      `(() => {
        const text = document.body.innerText
        return {
          rewards: text.includes('Crypto Rewards') && text.includes('Native rewards'),
          quantity: text.includes('9007199254740993.123456789'),
          fiat: text.includes('500.00'),
        }
      })()`
    )
    assert.deepEqual(probe, { rewards: true, quantity: true, fiat: true }, `${context}: crypto rewards verbatim`)
    assert.equal(
      await evalProbe(run, `document.body.innerText.includes('of 0 entries')`),
      true,
      `${context}: crypto activity shows the empty range state`,
    )
    await capture(run, 'crypto-desktop')

    // Failed then recovered resources: error alert, then recovery without
    // discarding siblings (request counts stay characterized).
    d7.failSecurityOnce = true
    await run(['open', `${appOrigin}/database/securities/2`])
    await waitFor(run, hasText('Unable to load part of this security'))
    await run(['wait', '300'])
    await capture(run, 'security-error')
    await run(['open', `${appOrigin}/database/securities/2`])
    await waitFor(run, hasText('Fixture Bond'))
    await run(['wait', '300'])

    // Missing security: explicit not-found alert.
    await run(['open', `${appOrigin}/database/securities/99`])
    await waitFor(run, hasText('Security not found or error loading data'))
    await run(['wait', '200'])

    void securityRequestsBefore
  }

  if (viewport.name !== 'desktop') {
    // Tablet/mobile probes: broker manager and bond page contained and
    // hittable; 768x1024 is verified by resizing inside the tablet phase.
    const width = viewport.width
    await run(['open', `${appOrigin}/profile/settings`])
    await waitFor(run, hasText('Broker API Tokens'))
    await run(['wait', '500'])
    await waitForBrokerPanels(run)
    await openProviderPanel(run, 'Tinkoff', context)
    // Rows render only after the token list resolves inside the open panel.
    await waitFor(run, hasText('Read Only Token'))
    await run(['wait', '300'])
    await assertFlowVisible(
      run,
      ['[data-testid="workspace-page-heading"]', '[data-testid="add-broker-token"]', 'button[aria-label="Deactivate token"]', 'button[aria-label="Check token validity"]'],
      `${context} broker manager`,
    )
    await capture(run, `broker-list-${viewport.name}`)

    if (viewport.name === 'tablet') {
      // The handoff requires 1024x768 AND 768x1024: resize the same session.
      await run(['set', 'viewport', '768', '1024'])
      await run(['wait', '400'])
      await assertFlowVisible(
        run,
        ['[data-testid="workspace-page-heading"]', '[data-testid="add-broker-token"]', 'button[aria-label="Deactivate token"]'],
        `${context} broker manager 768x1024`,
      )
      await run(['set', 'viewport', String(width), String(viewport.height)])
      await run(['wait', '300'])
    }

    await run(['open', `${appOrigin}/database/securities/2`])
    await waitFor(run, hasText('Fixture Bond'))
    await run(['wait', '500'])
    await assertFlowVisible(
      run,
      ['[data-testid="workspace-page-heading"]', 'section.workspace-section', 'canvas', '.v-data-table'],
      `${context} bond mobile`,
    )
    await capture(run, `bond-${viewport.name}`)
    console.log(`PASS ${context} brokers-security-d7 mobile probe`)
    return
  }

  // ---------- Desktop: broker connection flows ---------------------------
  await runSecurityFlows()

  await run(['open', `${appOrigin}/profile/settings`])
  await waitFor(run, hasText('Broker API Tokens'))
  await run(['wait', '500'])
  await waitForBrokerPanels(run)
  await openProviderPanel(run, 'Tinkoff', context)
  await waitFor(run, hasText('Read Only Token'))
  await run(['wait', '300'])
  const brokerProbe = await evalProbe(
    run,
    `(() => {
      const text = document.body.innerText
      const iconButtons = [...document.querySelectorAll('button[aria-label]')].map((b) => b.getAttribute('aria-label'))
      return {
        heading: text.includes('Broker API Tokens'),
        tinkoffRows: text.includes('Read Only Token'),
        tinkoffCount: text.includes('Tinkoff tokens (1)'),
        ibHidden: !text.includes('Interactive Brokers tokens (1)'),
        testButtons: iconButtons.filter((label) => label === 'Check token validity').length,
        deleteButtons: iconButtons.filter((label) => label === 'Delete token permanently').length,
      }
    })()`
  )
  assert.equal(brokerProbe.heading, true, `${context}: broker manager heading`)
  assert.equal(brokerProbe.tinkoffRows, true, `${context}: tinkoff rows render`)
  assert.equal(brokerProbe.tinkoffCount, true, `${context}: tinkoff count reflects the active filter`)
  assert.equal(brokerProbe.ibHidden, true, `${context}: IB rows hidden by default`)
  assert.equal(brokerProbe.testButtons, 1, `${context}: one visible test button (tinkoff active row)`)
  assert.equal(brokerProbe.deleteButtons, 0, `${context}: inactive rows hidden by default`)
  await assertFlowVisible(
    run,
    ['[data-testid="workspace-page-heading"]', 'button[aria-label="Check token validity"]', 'button[aria-label="Deactivate token"]'],
    `${context} broker list desktop`,
  )
  await capture(run, 'broker-list')

  // Bybit panel (single-open): row title and chip while it is expanded.
  await openProviderPanel(run, 'Bybit', context)
  const bybitProbe = await evalProbe(
    run,
    `(() => {
      const text = document.body.innerText
      return {
        bybitKey: text.includes('API key: bybit-synthetic-key'),
        testnet: text.includes('Testnet'),
        noTestButton: ![...document.querySelectorAll('button[aria-label]')]
          .some((b) => b.getAttribute('aria-label') === 'Check token validity'),
      }
    })()`
  )
  assert.deepEqual(
    bybitProbe,
    { bybitKey: true, testnet: true, noTestButton: true },
    `${context}: bybit row renders with chip and no test button`,
  )

  // Add Token: Tinkoff save with the exact recorded payload, auto test and
  // erased draft on reopen.
  await clickButtonByText(run, 'Add Token', context)
  await waitFor(run, hasText('Add New Token'))
  await chooseSelectOption(run, { label: 'Select Broker', option: 'Tinkoff', context })
  await run(['wait', '300'])
  await fillTextField(run, 'API Token', 'synthetic-tinkoff-token', context)
  const testCountBeforeSave = d7.tests.length
  await clickButtonByText(run, 'Save', context)
  // The save message is immediately replaced by the auto-test's message in
  // the single snackbar; the server records prove both happened.
  await waitFor(run, hasText('Connection test successful'))
  await run(['wait', '600'])
  const tinkoffSave = d7.saveBodies.at(-1)
  assert.deepEqual(
    tinkoffSave,
    { endpoint: 'tinkoff', body: { broker: 1, token: 'synthetic-tinkoff-token', token_type: 'read_only', sandbox_mode: false } },
    `${context}: exact tinkoff save payload`,
  )
  assert.equal(
    d7.tests.length - testCountBeforeSave,
    1,
    `${context}: post-save test fired exactly once`,
  )
  assert.ok(
    d7.tests.at(-1).endsWith('/77/test_connection/'),
    `${context}: post-save test targets the fresh token 77`,
  )
  const reopened = await evalProbe(
    run,
    `(() => {
      const add = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Add Token')
      add.click()
      return true
    })()`
  )
  assert.equal(reopened, true, `${context}: reopen add dialog`)
  await run(['wait', '400'])
  // With the draft erased no provider is selected, so the provider fields
  // are gone; choosing Tinkoff again must show an empty token input.
  const tokenBlank = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'API Token'))
      return field ? 'field-rendered-before-provider' : 'no-provider-fields'
    })()`
  )
  assert.equal(tokenBlank, 'no-provider-fields', `${context}: credential draft erased after success (no provider fields)`)
  await chooseSelectOption(run, { label: 'Select Broker', option: 'Tinkoff', context })
  await run(['wait', '300'])
  const tokenValueAfterReopen = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'API Token'))
      return field ? (field.querySelector('input')?.value ?? '') : null
    })()`
  )
  assert.equal(tokenValueAfterReopen, '', `${context}: reopened token input is empty`)

  // Rejected save keeps editable inputs; cancel sends nothing; the error
  // screenshot shows a masked (password) field only.
  d7.rejectNextSave = true
  await chooseSelectOption(run, { label: 'Select Broker', option: 'Tinkoff', context })
  await run(['wait', '300'])
  await fillTextField(run, 'API Token', 'synthetic-rejected-token', context)
  await clickButtonByText(run, 'Save', context)
  await waitFor(run, hasText('Token verification failed'))
  await run(['wait', '300'])
  const retained = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'API Token'))
      const input = field?.querySelector('input')
      return { open: !!input, value: input?.value ?? null, type: input?.type ?? null }
    })()`
  )
  assert.deepEqual(
    retained,
    { open: true, value: 'synthetic-rejected-token', type: 'password' },
    `${context}: rejected save retains the editable masked input`,
  )
  const savesBeforeCancel = d7.saveBodies.length
  await capture(run, 'broker-form-error-masked')
  await clickButtonByText(run, 'Cancel', context)
  await run(['wait', '400'])
  assert.equal(d7.saveBodies.length, savesBeforeCancel, `${context}: cancellation sends nothing`)
  const blankAfterCancel = await evalProbe(
    run,
    `(() => {
      const add = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Add Token')
      add.click()
      return true
    })()`
  )
  assert.equal(blankAfterCancel, true, `${context}: reopen after cancel`)
  await run(['wait', '400'])
  // No provider fields render until a broker is chosen — that IS the erased
  // state; choosing Tinkoff must reveal an empty token input.
  const blankValue = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'API Token'))
      return field ? 'field-rendered-before-provider' : 'no-provider-fields'
    })()`
  )
  assert.equal(blankValue, 'no-provider-fields', `${context}: cancel erases the draft (no provider fields)`)
  await chooseSelectOption(run, { label: 'Select Broker', option: 'Tinkoff', context })
  await run(['wait', '300'])
  const blankTokenValue = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'API Token'))
      return field ? (field.querySelector('input')?.value ?? '') : null
    })()`
  )
  assert.equal(blankTokenValue, '', `${context}: cancelled token value is gone`)
  await clickButtonByText(run, 'Cancel', context)
  await run(['wait', '300'])

  // Test command: exact endpoint, busy state, success notice. Reopen the
  // Tinkoff panel (single-open: Bybit took it) — the first visible test
  // control belongs to the still-active tinkoff row 11.
  await openProviderPanel(run, 'Tinkoff', context)
  const testCountBefore = d7.tests.length
  await clickIconButton(run, 'Check token validity', context, { which: 'first' })
  await waitFor(run, hasText('Connection test successful'))
  await run(['wait', '400'])
  assert.equal(d7.tests.length, testCountBefore + 1, `${context}: exactly one test request`)
  assert.ok(
    d7.tests.at(-1).endsWith('/11/test_connection/'),
    `${context}: test targets token 11`,
  )
  // The post-test list refresh rebuilds the expansion panels collapsed;
  // open Tinkoff again before targeting its rows.
  await openProviderPanel(run, 'Tinkoff', context)
  await waitFor(run, hasText('Read Only Token'))

  // Revoke: exact (provider, tokenId) body and refresh; the first visible
  // revoke control belongs to tinkoff row 11.
  const revokeCountBefore = d7.revokes.length
  await clickIconButton(run, 'Deactivate token', context, { which: 'first' })
  await waitFor(run, hasText('Token revoked successfully'))
  await run(['wait', '400'])
  assert.deepEqual(
    d7.revokes.slice(revokeCountBefore),
    [{ token_type: 'tinkoff', token_id: 11 }],
    `${context}: revoke body identity`,
  )

  // Destructive confirmation names the connection; cancel sends nothing;
  // confirm deletes exactly once. Opening the OKX panel closes Tinkoff
  // (single-open), so its controls become the visible delete targets.
  await openProviderPanel(run, 'OKX', context)
  const deletesBefore = d7.deletes.length
  // Reveal the inactive OKX row through the incumbent toggle.
  const toggled = await evalProbe(
    run,
    `(() => {
      const field = [...document.querySelectorAll('.v-input')]
        .find((el) => [...el.querySelectorAll('label')].some((l) => l.textContent.trim() === 'Show inactive tokens'))
      const box = field?.querySelector('input[type="checkbox"]')
      if (!box) return false
      box.click()
      return true
    })()`
  )
  assert.equal(toggled, true, `${context}: show-inactive toggled`)
  await run(['wait', '400'])
  await clickIconButton(run, 'Delete token permanently', context, { which: 'last' })
  await waitFor(run, hasText('Delete connection'))
  await run(['wait', '300'])
  const confirmation = await evalProbe(
    run,
    `(() => {
      const text = document.body.innerText
      return {
        subject: text.includes('OKX · API key: okx-synthetic-key (#31)'),
        scoped: text.includes('only the stored API credential'),
        portfolio: text.includes('portfolio transactions are not affected'),
        undo: text.includes('This action cannot be undone.'),
      }
    })()`
  )
  assert.deepEqual(
    confirmation,
    { subject: true, scoped: true, portfolio: true, undo: true },
    `${context}: exact destructive confirmation`,
  )
  await capture(run, 'delete-confirmation')
  await clickButtonByText(run, 'Cancel', context)
  await run(['wait', '300'])
  assert.equal(d7.deletes.length, deletesBefore, `${context}: cancelled deletion sends nothing`)
  const deletesBeforeConfirm = d7.deletes.length
  await clickIconButton(run, 'Delete token permanently', context, { which: 'last' })
  await waitFor(run, hasText('Delete connection'))
  await clickButtonByText(run, 'Delete', context)
  await waitFor(run, hasText('Token deleted successfully'))
  await run(['wait', '400'])
  const confirmDeletes = d7.deletes.slice(deletesBeforeConfirm)
  assert.equal(confirmDeletes.length, 1, `${context}: exactly one delete request (${JSON.stringify(confirmDeletes)})`)
  assert.equal(confirmDeletes[0].id, 31, `${context}: okx token deleted exactly once`)

  // ---------- Desktop→mobile→desktop transition on the broker manager ----
  await openProviderPanel(run, 'Tinkoff', context)
  await run(['set', 'viewport', '390', '844'])
  await run(['wait', '400'])
  await assertFlowVisible(
    run,
    ['[data-testid="workspace-page-heading"]'],
    `${context} broker manager desktop->mobile`,
  )
  await run(['set', 'viewport', '1440', '1000'])
  await run(['wait', '400'])
  await assertFlowVisible(
    run,
    ['[data-testid="workspace-page-heading"]', 'button[aria-label="Deactivate token"]'],
    `${context} broker manager mobile->desktop`,
  )

  // ---------- Native 200% zoom on the populated bond page ----------------
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

  await run(['open', `${appOrigin}/database/securities/2`])
  await waitFor(run, hasText('Fixture Bond'))
  await run(['wait', '400'])
  const zoomed = await zoomTo(200)
  assert.equal(zoomed.code, 0, `${context}: native 200% zoom verified (${zoomed.out.trim()})`)
  await run(['wait', '400'])
  const zoomProbe = await evalProbe(
    run,
    `(() => {
      const headerBottom = Math.max(0, ...[...document.querySelectorAll('.v-toolbar, .v-app-bar')]
        .filter((el) => { const s = getComputedStyle(el); return (s.position === 'fixed' || s.position === 'sticky') })
        .map((el) => el.getBoundingClientRect().bottom))
      const within = (el) => { const b = el.getBoundingClientRect(); return b.left >= -1 && b.right <= innerWidth + 1 }
      const hit = (el) => {
        const b = el.getBoundingClientRect()
        const h = document.elementFromPoint(b.left + b.width / 2, Math.min(Math.max(b.top + b.height / 2, headerBottom + 1), innerHeight - 1))
        return !!h && (el.contains(h) || h === el)
      }
      const heading = document.querySelector('[data-testid="workspace-page-heading"]')
      const canvas = document.querySelector('canvas')
      heading?.scrollIntoView({ block: 'center' })
      const headingOk = heading && within(heading) && hit(heading)
      canvas?.scrollIntoView({ block: 'center' })
      const canvasOk = canvas && within(canvas) && hit(canvas)
      return { dpr: window.devicePixelRatio, headingOk, canvasOk }
    })()`
  )
  assert.ok(zoomProbe.dpr >= 1.9, `${context}: devicePixelRatio is real browser zoom (${zoomProbe.dpr})`)
  assert.equal(zoomProbe.headingOk, true, `${context}: bond heading usable at 200%`)
  assert.equal(zoomProbe.canvasOk, true, `${context}: bond chart region usable at 200%`)
  await capture(run, 'zoom200-bond')
  const reset = await zoomTo(100)
  assert.equal(reset.code, 0, `${context}: zoom reset verified (${reset.out.trim()})`)
  const dprReset = await evalProbe(run, 'window.devicePixelRatio')
  assert.equal(dprReset, 1, `${context}: DPR reset to 1`)

  console.log(`PASS ${context} brokers-security-d7 rendered acceptance`)
}
