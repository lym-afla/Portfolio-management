// Absent-data breakdown-row rule (owner round-4 correction).
//
// The breakdown endpoint always emits every asset-class row plus the TOTAL
// row. The ONLY contractual absence encoding on this wire is the empty
// string (a Cash row's non-applicable cost/unrealized/realized cells) and
// its null/undefined equivalents. Numeric zero — raw or formatted ('$0.00',
// '0.0%', '($0.00)') — is meaningful data and is never treated as absence:
// wholly zero-valued rows remain visible, and zeros inside kept rows render
// verbatim. Status-style markers ('N/A', 'N/R', a bare dash) and any
// unparseable display count as meaningful. TOTAL rows are never hidden.
//
// Wire limitation (documented, not guessed around): the backend currently
// cannot distinguish "no activity in this class" from "genuine zero
// activity" — both arrive as all-zero displays — so ambiguous all-zero rows
// are deliberately PRESERVED until the backend gains an explicit absence
// marker. On today's wire no real row is fully empty (Cash always carries
// market_value/commission), so the filter is contract-complete but inert;
// it becomes active the moment the backend marks absence.
export const TOTAL_ROW_NAME = 'TOTAL'


export function isAbsentBreakdownCell(value) {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  return false
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
