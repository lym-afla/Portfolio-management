/**
 * Pivot helpers for the long-format FX model.
 *
 * The backend stores one row per (date, currency pair):
 * `{ id, date, from_currency, to_currency, rate }`. The `/database/fx` table
 * presents a wide grid (one row per date, one column per pair), so the
 * frontend pivots these rows. Pair columns are keyed as
 * `"from_currency/to_currency"` (e.g. `"USD/EUR"`), matching the table
 * headers, and each cell stores both the rate and the underlying row id so
 * edit/delete can target a specific record.
 */

// Canonical currency-pair order; keeps column ordering stable regardless of
// which pairs happen to be present on the current page. Pairs not listed here
// sort after the known ones, alphabetically.
export const PAIR_ORDER = [
  'USD/EUR',
  'USD/GBP',
  'CHF/GBP',
  'RUB/USD',
  'PLN/USD',
  'CNY/USD',
]

/**
 * Build the pair label (e.g. `"USD/EUR"`) for a long-format FX row.
 * @param {{ from_currency: string, to_currency: string }} row
 * @returns {string}
 */
export const pairLabelOf = (row) => `${row.from_currency}/${row.to_currency}`

/**
 * Inverse of {@link pairLabelOf}: split a pair label into `[from, to]`.
 * Returns `['', '']` for a malformed (slashless) label so callers can destructure
 * safely. Used by per-cell editing to derive a cell's currency pair.
 * @param {string} pairLabel e.g. "USD/EUR"
 * @returns {[string, string]}
 */
export const splitPairLabel = (pairLabel) => {
  const idx = pairLabel.indexOf('/')
  return idx === -1
    ? ['', '']
    : [pairLabel.slice(0, idx), pairLabel.slice(idx + 1)]
}

/**
 * Compare two pair labels, preserving {@link PAIR_ORDER} for known pairs and
 * sorting unknown ones alphabetically after the known set.
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
export const comparePairLabels = (a, b) => {
  const ia = PAIR_ORDER.indexOf(a)
  const ib = PAIR_ORDER.indexOf(b)
  if (ia === -1 && ib === -1) return a.localeCompare(b)
  if (ia === -1) return 1
  if (ib === -1) return -1
  return ia - ib
}

/**
 * Pivot long-format FX rows into a wide grid: one row per date, one property
 * per currency pair. Missing pairs are simply absent from the row object, so
 * the template renders them with its `?? '—'` fallback.
 *
 * @param {Array<{id:number, date:string, from_currency:string, to_currency:string, rate:string}>} rows
 * @returns {{ pivoted: Array<object>, pairLabels: string[] }}
 *   `pivoted` rows look like `{ date, "USD/EUR": { rate, id }, ... }`;
 *   `pairLabels` is the ordered list of pair-column keys.
 */
export const pivotFxRows = (rows) => {
  const byDate = new Map()
  const pairSet = new Set()
  for (const row of rows || []) {
    if (!row || !row.date) continue
    const pairLabel = pairLabelOf(row)
    pairSet.add(pairLabel)
    if (!byDate.has(row.date)) {
      byDate.set(row.date, { date: row.date })
    }
    byDate.get(row.date)[pairLabel] = { rate: row.rate, id: row.id }
  }
  const pivoted = [...byDate.values()]
  const pairLabels = [...pairSet].sort(comparePairLabels)
  return { pivoted, pairLabels }
}

/**
 * Given a pivoted row, return the first currency-pair record present (in
 * column order). A pivoted row represents several FX records for one date, so
 * edit/delete operate on the first available pair as a non-regressive default.
 *
 * @param {object} item pivoted row
 * @param {string[]} [pairLabels] column order; defaults to {@link PAIR_ORDER}
 * @returns {{ id:number, from_currency:string, to_currency:string, rate:string, date:string } | null}
 */
export const firstPairInRow = (item, pairLabels = PAIR_ORDER) => {
  for (const pairLabel of pairLabels) {
    const entry = item?.[pairLabel]
    if (entry && entry.id != null) {
      const [from_currency, to_currency] = pairLabel.split('/')
      return { ...entry, from_currency, to_currency, date: item.date }
    }
  }
  return null
}
