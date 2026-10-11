// Task 1 (real-data corrections): the header valuation date commits through
// the shared context-change owner exactly once per accepted change. Native
// date inputs fire `change` on every segment edit, so keyboard interaction
// arms a guard: typed intermediate dates defer to the blur/Enter commit,
// while a calendar-picker selection (no keydown) commits immediately.
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

  it('commits an unarmed change immediately (calendar-picker path)', async () => {
    const harness = makeHarness('2026-10-09')
    harness.dateDraft.value = '2024-06-30'
    expect(await harness.commitDateChange()).toBe('2024-06-30')
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
  })

  it('defers a keyboard-armed change to the blur/Enter commit (typed segment path)', async () => {
    const harness = makeHarness('2026-10-09')
    harness.markKeyboardEditing()
    harness.dateDraft.value = '2025-01-08'
    expect(await harness.commitDateChange()).toBeNull()
    expect(harness.requestContextChange).not.toHaveBeenCalled()
    // The completed typed date commits exactly once through blur/Enter.
    harness.dateDraft.value = '2025-12-31'
    expect(await harness.saveDate()).toBe('2025-12-31')
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
  })

  it('re-arms per keystroke: a picker change after typing still commits', async () => {
    const harness = makeHarness('2026-10-09')
    harness.markKeyboardEditing()
    harness.dateDraft.value = '2025-01-08'
    expect(await harness.commitDateChange()).toBeNull()
    expect(harness.requestContextChange).not.toHaveBeenCalled()
    // New picker selection: no keydown preceded it.
    harness.dateDraft.value = '2024-06-30'
    expect(await harness.commitDateChange()).toBe('2024-06-30')
    expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
  })

  it('disarms after the keystroke task: a segment move cannot suppress a later selection', async () => {
    vi.useFakeTimers()
    try {
      const harness = makeHarness('2026-10-09')
      // A keydown that changes no value (segment move) arms the guard, but
      // the arm expires on the next macrotask — the change it covered never
      // arrives, and a later calendar-picker selection must still commit.
      harness.markKeyboardEditing()
      await vi.advanceTimersByTimeAsync(0)
      harness.dateDraft.value = '2024-06-30'
      expect(await harness.commitDateChange()).toBe('2024-06-30')
      expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps the arm across the keystroke task so typed intermediates still defer', async () => {
    vi.useFakeTimers()
    try {
      const harness = makeHarness('2026-10-09')
      harness.markKeyboardEditing()
      harness.dateDraft.value = '2025-01-08'
      // Same macrotask as the keystroke: not yet disarmed.
      expect(await harness.commitDateChange()).toBeNull()
      expect(harness.requestContextChange).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(0)
      // The completed typed value commits through blur/Enter exactly once.
      harness.dateDraft.value = '2025-12-31'
      expect(await harness.saveDate()).toBe('2025-12-31')
      expect(harness.requestContextChange).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
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
