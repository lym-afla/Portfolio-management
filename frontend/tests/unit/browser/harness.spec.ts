import { describe, expect, it } from 'vitest'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  cleanupBrowserHarness,
  runBrowserHarnessLifecycle,
} from '../../../tests/browser/lifecycle.mjs'
import { parseCliResult } from '../../../tests/browser/protocol.mjs'
import { resolveFixture } from '../../../tests/browser/fixtures.mjs'
import { routes, viewports } from '../../../tests/browser/routes.mjs'
import {
  D8_FLAG_KEYS,
  hashArtifact,
  scanFlagEnvFiles,
  withFlagEnvironment,
} from '../../../tests/browser/artifact-flags.mjs'

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

describe('D8 release-flag artifact selection', () => {
  it('targets the three real release-flag keys', () => {
    expect(D8_FLAG_KEYS).toEqual([
      'VITE_NAV_ECHARTS_ENABLED',
      'VITE_ALLOCATION_ECHARTS_ENABLED',
      'VITE_SECURITY_ECHARTS_ENABLED',
    ])
  })

  it('restores the environment after a build, with absent keys genuinely deleted', async () => {
    process.env.D8_SPEC_UNRELATED = 'untouched'
    process.env.D8_SPEC_EXISTING = 'before'
    try {
      const seen = await withFlagEnvironment(
        {
          VITE_NAV_ECHARTS_ENABLED: null,
          VITE_ALLOCATION_ECHARTS_ENABLED: 'false',
          VITE_SECURITY_ECHARTS_ENABLED: 'true',
          D8_SPEC_EXISTING: 'during',
        },
        async () => ({
          navAbsent: process.env.VITE_NAV_ECHARTS_ENABLED === undefined,
          allocation: process.env.VITE_ALLOCATION_ECHARTS_ENABLED,
          security: process.env.VITE_SECURITY_ECHARTS_ENABLED,
          existing: process.env.D8_SPEC_EXISTING,
          unrelated: process.env.D8_SPEC_UNRELATED,
        }),
      )
      expect(seen).toEqual({
        navAbsent: true,
        allocation: 'false',
        security: 'true',
        existing: 'during',
        unrelated: 'untouched',
      })
      // A null flag must be ABSENT again afterwards, not an empty string —
      // the default-on candidate is selected by genuine absence.
      expect(process.env.VITE_NAV_ECHARTS_ENABLED).toBeUndefined()
      expect(process.env.VITE_ALLOCATION_ECHARTS_ENABLED).toBeUndefined()
      expect(process.env.VITE_SECURITY_ECHARTS_ENABLED).toBeUndefined()
      expect(process.env.D8_SPEC_EXISTING).toBe('before')
      expect(process.env.D8_SPEC_UNRELATED).toBe('untouched')
    } finally {
      delete process.env.D8_SPEC_UNRELATED
      delete process.env.D8_SPEC_EXISTING
    }
  })

  it('restores the environment even when the build fails', async () => {
    process.env.VITE_NAV_ECHARTS_ENABLED = 'false'
    try {
      const failure = new Error('build failed')
      await expect(
        withFlagEnvironment({ VITE_NAV_ECHARTS_ENABLED: null }, async () => {
          expect(process.env.VITE_NAV_ECHARTS_ENABLED).toBeUndefined()
          throw failure
        }),
      ).rejects.toBe(failure)
      expect(process.env.VITE_NAV_ECHARTS_ENABLED).toBe('false')
    } finally {
      delete process.env.VITE_NAV_ECHARTS_ENABLED
    }
  })

  it('reports release flags defined in any env file and tolerates comments', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'd8-env-scan-'))
    try {
      await writeFile(
        join(dir, '.env.local'),
        '# comment\nVITE_API_URL=http://127.0.0.1:8000\nVITE_NAV_ECHARTS_ENABLED="false"\n',
        'utf8',
      )
      await writeFile(join(dir, '.env'), 'VITE_ALLOCATION_ECHARTS_ENABLED=false\n', 'utf8')
      const scan = await scanFlagEnvFiles(dir)
      expect(scan.flagKeysFound).toEqual([
        { file: '.env', key: 'VITE_ALLOCATION_ECHARTS_ENABLED', value: 'false' },
        { file: '.env.local', key: 'VITE_NAV_ECHARTS_ENABLED', value: 'false' },
      ])
      expect(scan.files.map((file) => file.file).sort()).toEqual(['.env', '.env.local'])
    } finally {
      await rm(dir, { recursive: true, force: true })
    }
  })

  it('hashes an artifact deterministically and reacts to content changes', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'd8-hash-'))
    try {
      await writeFile(join(dir, 'a.txt'), 'alpha', 'utf8')
      await writeFile(join(dir, 'sub.txt'), 'beta', 'utf8')
      const first = await hashArtifact(dir)
      const second = await hashArtifact(dir)
      expect(second).toEqual(first)
      expect(first.files).toBe(2)
      expect(first.bytes).toBe('alpha'.length + 'beta'.length)
      await writeFile(join(dir, 'a.txt'), 'gamma', 'utf8')
      const changed = await hashArtifact(dir)
      expect(changed.sha256).not.toBe(first.sha256)
    } finally {
      await rm(dir, { recursive: true, force: true })
    }
  })
})
