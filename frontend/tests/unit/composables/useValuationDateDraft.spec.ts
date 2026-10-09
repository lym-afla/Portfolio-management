// Task 1 (real-data corrections): the header valuation date commits through
// the shared context-change owner exactly once per accepted change — from the
// calendar picker (update:model-value) or from typing plus blur/Enter.
// Invalid or incomplete drafts never commit; a rejected update restores the
// committed date.
import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import {
  completeIsoDateOrNull,
  useValuationDateDraft,
} from '@/composables/useValuationDateDraft'

describe('completeIsoDateOrNull', () => {
  it('accepts a complete real calendar date', () => {
    expect(completeIsoDateOrNull('2024-06-30')).toBe('2024-06-30')
  })

  it('rejects incomplete, malformed and impossible dates', () => {
    expect(completeIsoDateOrNull('')).toBeNull()
    expect(completeIsoDateOrNull('2024-06')).toBeNull()
    expect(completeIsoDateOrNull('2024-06-3')).toBeNull()
    expect(completeIsoDateOrNull('06/30/2024')).toBeNull()
    expect(completeIsoDateOrNull('2024-02-30')).toBeNull()
    expect(completeIsoDateOrNull('2024-13-01')).toBeNull()
  })
})

describe('useValuationDateDraft', () => {
  const makeHarness = (committed: string | null, requestContextChange = vi.fn().mockResolvedValue(undefined)) => {
    const committedRef = ref(committed)
    const harness = useValuationDateDraft({
      committed: committedRef,
      canRead: () => true,
      requestContextChange,
    })
    return { ...harness, committedRef, requestContextChange }
  }

  it('commits a valid calendar-picked date exactly once through the context owner', async () => {
    const harness = makeHarness('2026-10-09')
    harness.dateDraft.value = '2024-06-30'
    const committedDate = await harness.saveDate()
    expect(committedDate).toBe('2024-06-30')
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
    expect(harness.requestContextChange).toHaveBeenCalledWith({ effectiveCurrentDate: '2024-06-30' })
  })

  it('does not commit an invalid or incomplete typed draft', async () => {
    const harness = makeHarness('2026-10-09')
    harness.dateDraft.value = ''
    expect(await harness.saveDate()).toBeNull()
    harness.dateDraft.value = '2024-06'
    expect(await harness.saveDate()).toBeNull()
    harness.dateDraft.value = '2024-02-30'
    expect(await harness.saveDate()).toBeNull()
    expect(harness.requestContextChange).not.toHaveBeenCalled()
  })

  it('treats an unchanged draft as a no-op (blur/Enter after a calendar pick never re-commits)', async () => {
    const harness = makeHarness('2026-10-09')
    harness.dateDraft.value = '2024-06-30'
    await harness.saveDate()
    harness.committedRef.value = '2024-06-30'
    await nextTick()
    expect(harness.dateDraft.value).toBe('2024-06-30')
    expect(await harness.saveDate()).toBeNull()
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
  })

  it('restores the committed date when the context change is rejected', async () => {
    const harness = makeHarness('2026-10-09', vi.fn().mockRejectedValue(new Error('rejected')))
    harness.dateDraft.value = '2024-06-30'
    expect(await harness.saveDate()).toBeNull()
    expect(harness.dateDraft.value).toBe('2026-10-09')
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
  })

  it('does not commit when the context is not readable', async () => {
    const requestContextChange = vi.fn().mockResolvedValue(undefined)
    const harness = useValuationDateDraft({
      committed: ref('2026-10-09'),
      canRead: () => false,
      requestContextChange,
    })
    harness.dateDraft.value = '2024-06-30'
    expect(await harness.saveDate()).toBeNull()
    expect(requestContextChange).not.toHaveBeenCalled()
  })
})
