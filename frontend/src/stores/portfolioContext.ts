import { computed, readonly, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { getPortfolioContextBackend } from '@/services/api/context'
import { apiGet } from '@/services/http/client'
import { ApiError } from '@/services/http/errors'
import { isRecord } from '@/types/portfolioTables'
import type {
  AccountSelection,
  PortfolioContext,
} from '@/types/portfolioContext'

export type ContextPatch = Readonly<Partial<Omit<PortfolioContext, 'revision'>>>
function selection(value: unknown): value is AccountSelection {
  return (
    isRecord(value) &&
    ((value.type === 'all' && value.id === null) ||
      (['account', 'broker', 'group'].includes(String(value.type)) &&
        Number.isInteger(value.id) &&
        Number(value.id) > 0))
  )
}
function cachedSelection(): AccountSelection {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem('accountSelection') || 'null'
    )
    if (selection(value)) return value
  } catch {
    /* Invalid cache is never authoritative. */
  }
  localStorage.removeItem('accountSelection')
  return { type: 'all', id: null }
}
function snapshot(value: PortfolioContext): PortfolioContext {
  return Object.freeze({
    ...value,
    accountSelection: Object.freeze({ ...value.accountSelection }),
  })
}
function validDate(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  )
}
export const usePortfolioContextStore = defineStore('portfolioContext', () => {
  const committed = shallowRef<PortfolioContext>(
    snapshot({
      revision: 0,
      accountSelection: cachedSelection(),
      effectiveCurrentDate: null,
      currency: null,
      digits: 2,
    })
  )
  const isReady = ref(false)
  const isTransitioning = ref(false)
  const transitionError = shallowRef<Error | null>(null)
  const dataRefreshTrigger = ref(0)
  const accountOptions = shallowRef<unknown[]>([])
  const currencyChoices = shallowRef<Array<{ value: string; text: string }>>([])
  const canRead = computed(() => isReady.value && !isTransitioning.value)
  let selections: AccountSelection[] = []
  let epoch = 0
  let pending = 0
  let queue: Promise<void> = Promise.resolve()
  const assertSession = (generation: number) => {
    if (generation !== epoch) throw new Error('Portfolio session ended')
  }
  function begin() {
    isTransitioning.value = true
    transitionError.value = null
    committed.value = snapshot({
      ...committed.value,
      revision: committed.value.revision + 1,
    })
  }
  async function readAndCommit(generation: number) {
    const [values, accounts, dashboard] = await Promise.all([
      getPortfolioContextBackend().read(),
      apiGet('/users/api/get_account_choices/'),
      apiGet('/users/api/dashboard_settings/'),
    ])
    assertSession(generation)
    if (
      !isRecord(accounts) ||
      !Array.isArray(accounts.options) ||
      !isRecord(dashboard) ||
      !isRecord(dashboard.choices) ||
      !Array.isArray(dashboard.choices.default_currency)
    )
      throw new Error('Invalid portfolio context choices')
    const available: AccountSelection[] = []
    function collect(value: unknown) {
      if (selection(value))
        available.push({ type: value.type, id: value.id } as AccountSelection)
      else if (Array.isArray(value)) value.forEach(collect)
    }
    collect(accounts.options)
    const currencies = dashboard.choices.default_currency.map(
      (item: unknown) => {
        if (
          !Array.isArray(item) ||
          typeof item[0] !== 'string' ||
          typeof item[1] !== 'string'
        )
          throw new Error('Invalid currency choices')
        return { value: item[0], text: item[1] }
      }
    )
    if (
      !selection(values.accountSelection) ||
      (values.effectiveCurrentDate !== null &&
        !validDate(values.effectiveCurrentDate)) ||
      !currencies.some((item) => item.value === values.currency) ||
      !Number.isInteger(values.digits) ||
      values.digits < 0 ||
      values.digits > 6
    )
      throw new Error('Invalid canonical portfolio context')
    selections = available
    accountOptions.value = accounts.options
    currencyChoices.value = currencies
    committed.value = snapshot({
      ...values,
      revision: committed.value.revision,
    })
    localStorage.setItem(
      'accountSelection',
      JSON.stringify(values.accountSelection)
    )
    isReady.value = true
  }
  function enqueue(work: (generation: number) => Promise<void>): Promise<void> {
    const generation = epoch
    const first = pending++ === 0
    const run = async () => {
      assertSession(generation)
      begin()
      try {
        await work(generation)
      } catch (error) {
        if (generation === epoch)
          transitionError.value =
            error instanceof Error ? error : new Error(String(error))
        throw error
      } finally {
        if (generation === epoch) {
          pending--
          isTransitioning.value = pending > 0
          if (!isTransitioning.value && isReady.value)
            dataRefreshTrigger.value++
        }
      }
    }
    const operation = first ? run() : queue.then(run)
    queue = operation.catch(() => undefined)
    return operation
  }
  function reconcileContext(): Promise<void> {
    return enqueue(async (generation) => {
      isReady.value = false
      await readAndCommit(generation)
    })
  }
  function changeContext(patch: ContextPatch): Promise<void> {
    const copy = Object.freeze({
      ...patch,
      ...(patch.accountSelection
        ? { accountSelection: Object.freeze({ ...patch.accountSelection }) }
        : {}),
    })
    return enqueue(async (generation) => {
      if (!isReady.value) await readAndCommit(generation)
      assertSession(generation)
      const next = { ...committed.value, ...copy }
      if (
        copy.accountSelection &&
        (!selection(copy.accountSelection) ||
          !selections.some(
            (item) =>
              item.type === copy.accountSelection?.type &&
              item.id === copy.accountSelection.id
          ))
      )
        throw new Error('Choose an available account, broker or group')
      const settingsChanged =
        'effectiveCurrentDate' in copy || 'currency' in copy || 'digits' in copy
      if (
        settingsChanged &&
        (!validDate(next.effectiveCurrentDate) ||
          !currencyChoices.value.some((item) => item.value === next.currency) ||
          !Number.isInteger(next.digits) ||
          next.digits < 0 ||
          next.digits > 6)
      )
        throw new Error(
          'Choose a valid date, currency and number of digits (0–6)'
        )
      let accountCompleted = false
      try {
        if (copy.accountSelection) {
          await getPortfolioContextBackend().updateAccount(
            copy.accountSelection
          )
          accountCompleted = true
          assertSession(generation)
        }
        if (settingsChanged) {
          await getPortfolioContextBackend().updateSettings({
            effectiveCurrentDate: next.effectiveCurrentDate!,
            currency: next.currency!,
            digits: next.digits,
          })
          assertSession(generation)
        }
        isReady.value = false
        await readAndCommit(generation)
      } catch (error) {
        assertSession(generation)
        // Only an explicitly rejected mutation POST is known not to have persisted.
        // A prior account write or subsequent refresh/readback failure is ambiguous.
        const rejected =
          !accountCompleted &&
          error instanceof ApiError &&
          error.code === 'context_mutation_rejected'
        if (!rejected) {
          isReady.value = false
          try {
            await readAndCommit(generation)
          } catch {
            /* Recovery remains disabled until a later explicit reconciliation succeeds. */
          }
          assertSession(generation)
        }
        throw error
      }
    })
  }
  function resetContext() {
    epoch++
    pending = 0
    queue = Promise.resolve()
    isReady.value = false
    isTransitioning.value = false
    transitionError.value = null
    selections = []
    accountOptions.value = []
    currencyChoices.value = []
    committed.value = snapshot({
      revision: committed.value.revision + 1,
      accountSelection: { type: 'all', id: null },
      effectiveCurrentDate: null,
      currency: null,
      digits: 2,
    })
    localStorage.removeItem('accountSelection')
  }
  function triggerDataRefresh() {
    if (canRead.value) dataRefreshTrigger.value++
  }
  return {
    committed: readonly(committed),
    isReady: readonly(isReady),
    isTransitioning: readonly(isTransitioning),
    transitionError: readonly(transitionError),
    canRead,
    accountOptions: readonly(accountOptions),
    currencyChoices: readonly(currencyChoices),
    dataRefreshTrigger: readonly(dataRefreshTrigger),
    changeContext,
    reconcileContext,
    resetContext,
    triggerDataRefresh,
  }
})
