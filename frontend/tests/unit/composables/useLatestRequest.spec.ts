import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { deferred } from '../helpers/deferred'
import { useLatestRequest } from '@/composables/useLatestRequest'

const snapshot = (params: { search: string }) => Object.freeze({ ...params })

describe('useLatestRequest', () => {
  it('accepts the latest response when the old transport ignores abort', async () => {
    const old = deferred<string[]>()
    const current = deferred<string[]>()
    const fetcher = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const query = useLatestRequest(fetcher, snapshot)
    const first = query.run({ search: 'old' })
    const second = query.run({ search: 'new' })
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
    current.resolve(['new result'])
    expect(await second).toEqual({ status: 'accepted', data: ['new result'] })
    old.resolve(['old result'])
    expect(await first).toEqual({ status: 'discarded' })
    expect(query.data.value).toEqual(['new result'])
    expect(query.loading.value).toBe(false)
  })

  it('does not let an older completion clear the newer loading state', async () => {
    const old = deferred<string[]>()
    const current = deferred<string[]>()
    const fetcher = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const query = useLatestRequest(fetcher, snapshot)
    const first = query.run({ search: 'old' })
    const second = query.run({ search: 'new' })
    old.resolve(['old result'])
    expect((await first).status).toBe('discarded')
    expect(query.loading.value).toBe(true)
    current.resolve(['new result'])
    await second
    expect(query.loading.value).toBe(false)
  })

  it('ignores an older rejection after current success', async () => {
    const old = deferred<string[]>()
    const current = deferred<string[]>()
    const query = useLatestRequest(vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise), snapshot)
    const first = query.run({ search: 'old' })
    const second = query.run({ search: 'new' })
    current.resolve(['new result'])
    await second
    old.reject(new Error('obsolete failure'))
    expect((await first).status).toBe('discarded')
    expect(query.error.value).toBeNull()
    expect(query.data.value).toEqual(['new result'])
  })

  it('invalidates pending work and silently discards its abort rejection', async () => {
    const pending = deferred<string[]>()
    const fetcher = vi.fn().mockReturnValue(pending.promise)
    const query = useLatestRequest(fetcher, snapshot)
    const running = query.run({ search: 'old' })
    query.invalidate()
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
    expect(query.loading.value).toBe(false)
    expect(query.data.value).toBeNull()
    pending.reject(new DOMException('aborted', 'AbortError'))
    expect((await running).status).toBe('discarded')
    expect(query.error.value).toBeNull()
  })

  it('recovers from failure with a later successful request', async () => {
    const failure = new Error('temporary failure')
    const fetcher = vi.fn().mockRejectedValueOnce(failure).mockResolvedValueOnce(['recovered'])
    const query = useLatestRequest(fetcher, snapshot)
    expect(await query.run({ search: 'same' })).toEqual({ status: 'failed', error: failure })
    expect(query.error.value).toBe(failure)
    expect(await query.run({ search: 'same' })).toEqual({ status: 'accepted', data: ['recovered'] })
    expect(query.error.value).toBeNull()
    expect(query.data.value).toEqual(['recovered'])
  })

  it('passes a captured nested parameter snapshot to transport', async () => {
    const pending = deferred<string[]>()
    const fetcher = vi.fn().mockReturnValue(pending.promise)
    const query = useLatestRequest(fetcher, (params: { search: string; sort: { key: string } }) =>
      Object.freeze({ ...params, sort: Object.freeze({ ...params.sort }) })
    )
    const params = { search: 'original', sort: { key: 'name' } }
    const running = query.run(params)
    params.search = 'changed'
    params.sort.key = 'price'
    expect(fetcher.mock.calls[0][0]).toEqual({ search: 'original', sort: { key: 'name' } })
    pending.resolve(['result'])
    await running
  })

  it('disposes pending work and cannot start another read after scope disposal', async () => {
    const pending = deferred<string[]>()
    const fetcher = vi.fn().mockReturnValue(pending.promise)
    const scope = effectScope()
    const query = scope.run(() => useLatestRequest(fetcher, snapshot))!
    const running = query.run({ search: 'old' })
    scope.stop()
    pending.resolve(['old result'])
    expect((await running).status).toBe('discarded')
    expect(query.data.value).toBeNull()
    expect((await query.run({ search: 'unmounted' })).status).toBe('discarded')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
