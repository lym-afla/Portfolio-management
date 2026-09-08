import { describe, expect, it } from 'vitest'

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
