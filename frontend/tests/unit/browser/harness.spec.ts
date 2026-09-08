import { describe, expect, it } from 'vitest'

import {
  cleanupBrowserHarness,
  runBrowserHarnessLifecycle,
} from '../../../tests/browser/lifecycle.mjs'
import { parseCliResult } from '../../../tests/browser/protocol.mjs'
import { resolveFixture } from '../../../tests/browser/fixtures.mjs'
import { routes, viewports } from '../../../tests/browser/routes.mjs'

describe('browser protocol', () => {
  it('parses the installed agent-browser success envelope', () => {
    expect(
      parseCliResult(
        '{"success":true,"data":{"result":{"path":"/dashboard"}},"error":null}\n',
        'route probe',
      ),
    ).toEqual({ result: { path: '/dashboard' } })
  })

  it('rejects failed agent-browser envelopes with their error', () => {
    expect(() =>
      parseCliResult(
        '{"success":false,"data":null,"error":"browser unavailable"}\n',
        'route probe',
      ),
    ).toThrow('route probe: browser unavailable')
  })
})

describe('browser lifecycle', () => {
  it('rejects a failed session close after attempting every later cleanup', async () => {
    const calls: string[] = []
    const closeFailure = new Error('first session stayed open')

    await expect(
      runBrowserHarnessLifecycle({
        run: async () => undefined,
        cleanup: () =>
          cleanupBrowserHarness({
            sessions: new Map([
              ['first', undefined],
              ['second', 'auth-init.js'],
            ]),
            closeSession: async (session: string) => {
              calls.push(`session:${session}`)
              if (session === 'first') {
                throw closeFailure
              }
            },
            closeAppServer: async () => {
              calls.push('app-server')
            },
            closeFixtureServer: async () => {
              calls.push('fixture-server')
            },
            recordError: async () => {
              calls.push('record-error')
            },
          }),
      })
    ).rejects.toMatchObject({
      errors: [expect.objectContaining({ cause: closeFailure })],
    })

    expect(calls).toEqual([
      'session:first',
      'record-error',
      'session:second',
      'app-server',
      'fixture-server',
    ])
  })

  it('keeps normal cleanup green', async () => {
    const calls: string[] = []

    await expect(
      runBrowserHarnessLifecycle({
        run: async () => calls.push('run'),
        cleanup: () =>
          cleanupBrowserHarness({
            sessions: new Map([['only', undefined]]),
            closeSession: async (session: string) => {
              calls.push(`session:${session}`)
            },
            closeAppServer: async () => {
              calls.push('app-server')
            },
            closeFixtureServer: async () => {
              calls.push('fixture-server')
            },
            recordError: async () => undefined,
          }),
      })
    ).resolves.toBeUndefined()

    expect(calls).toEqual([
      'run',
      'session:only',
      'app-server',
      'fixture-server',
    ])
  })

  it('preserves the original run failure when cleanup also fails', async () => {
    const runFailure = new Error('route assertion failed')
    const cleanupFailure = new Error('session close failed')

    const result = runBrowserHarnessLifecycle({
      run: async () => {
        throw runFailure
      },
      cleanup: async () => {
        throw cleanupFailure
      },
    })

    await expect(result).rejects.toMatchObject({
      cause: runFailure,
      errors: [runFailure, cleanupFailure],
    })
  })
})

describe('fixture contract', () => {
  it('returns the complete authenticated profile fixture', () => {
    expect(resolveFixture('GET', '/users/api/profile/')).toMatchObject({
      status: 200,
      body: {
        username: 'fixture-user',
        selected_account_type: 'all',
        selected_account_id: null,
      },
    })
  })

  it('rejects every unmatched request including mutations', () => {
    expect(() => resolveFixture('POST', '/users/api/unmatched-mutation/')).toThrow(
      'Unmatched fixture request: POST /users/api/unmatched-mutation/',
    )
  })
})

describe('route matrix', () => {
  it('enumerates every production route and required viewport', () => {
    expect(routes.map((route) => route.path)).toEqual([
      '/',
      '/login',
      '/register',
      '/dashboard',
      '/open-positions',
      '/closed-positions',
      '/transactions',
      '/profile',
      '/profile/edit',
      '/profile/settings',
      '/database',
      '/database/brokers',
      '/database/accounts',
      '/database/prices',
      '/database/securities',
      '/database/securities/1',
      '/database/fx',
      '/summary',
    ])
    expect(viewports).toEqual([
      { name: 'desktop', width: 1440, height: 1000, zoom: 1 },
      { name: 'tablet', width: 1024, height: 768, zoom: 1 },
      { name: 'mobile', width: 390, height: 844, zoom: 1 },
      { name: 'zoom-200', width: 1440, height: 1000, zoom: 2 },
    ])
  })
})
