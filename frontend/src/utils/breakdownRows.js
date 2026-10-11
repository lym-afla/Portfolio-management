// Absent-data breakdown-row rule (owner: "Portfolio breakdown works. I
// would hide rows with no data").
//
// The breakdown endpoint always emits every asset-class row plus the TOTAL
// row, so classes the portfolio holds nothing in arrive as rows whose every
// cell carries an absence encoding of this contract: an empty string (the
// non-applicable cells, e.g. a Cash row's cost/unrealized/realized) or a
// numeric-zero display ('$0.00', '0.0%', '($0.00)'). Such a row is hidden.
// A row that carries any real information is kept and every cell renders
// verbatim — numeric zeros inside a kept row are never blanked, and
// status-style markers ('N/A', 'N/R', a bare dash) count as meaningful.
// TOTAL rows are always kept.
export const TOTAL_ROW_NAME = 'TOTAL'

// A bare dash is a status marker; signed/currency-wrapped zero displays are
// absence encodings.
const STATUS_MARKER = /^(?:n\/?a|n\/r|—|–|-)$/i
const ZERO_DISPLAY = /^-?\(?\$?\s*0+(?:[.,]0+)*\s*\)?%?$/

export function isAbsentBreakdownCell(value) {
  if (value === null || value === undefined) return true
  if (typeof value === 'number') return value === 0
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (text === '') return true
  if (STATUS_MARKER.test(text)) return false
  return ZERO_DISPLAY.test(text)
}

export function isAbsentBreakdownRow(row) {
  if (!row || typeof row !== 'object') return false
  if (row.name === TOTAL_ROW_NAME) return false
  return Object.entries(row).every(
    ([key, value]) => key === 'name' || isAbsentBreakdownCell(value)
  )
}

export function visibleBreakdownRows(rows) {
  if (!Array.isArray(rows)) return rows
  return rows.filter((row) => !isAbsentBreakdownRow(row))
}
