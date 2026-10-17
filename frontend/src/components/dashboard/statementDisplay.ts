// Display-layer cross-check for the reconciled statement: the backend's
// display strings are independently rounded per row, so the shown components
// can differ from the shown subtotal by a display unit. The check parses the
// ALREADY-FORMATTED display strings into scaled BigInt integers (never
// floats) and reports the difference; raw financial values are never routed
// through this helper.

export interface DisplayAmount {
  display: string
}

/**
 * Parse a backend currency display string ("$1,234.56", "($5.00)", "–")
 * into an integer scaled by 10^digits. Returns null for unparseable text.
 */
export function parseDisplayScaled(display: string, digits: number): bigint | null {
  const text = display.trim()
  if (text === '') return null
  // The backend renders a genuine ZERO as the en-dash marker; textual
  // unavailable markers (N/A, NA, N/R) are MISSING values and must never
  // be treated as zero.
  if (text === '–') return BigInt(0)
  if (text === 'N/A' || text === 'NA' || text === 'N/R') return null

  const match = /^(\()?\$?€?£?¥?([0-9][0-9,]*(?:\.[0-9]+)?)(\))?$/.exec(text)
  if (!match) return null
  const negative = match[1] === '(' || match[3] === ')'
  const unsigned = match[2].replaceAll(',', '')
  const [intPart, fracPart = ''] = unsigned.split('.')
  const scaledFrac = (fracPart + '0'.repeat(digits)).slice(0, Math.max(digits, 0))
  const scaled = BigInt(intPart + scaledFrac || '0')
  return negative ? -scaled : scaled
}

/**
 * Format a BigInt scaled by 10^digits back into a plain display number with
 * thousands grouping (no currency symbol) — display-only.
 */
export function formatScaledInteger(value: bigint, digits: number): string {
  const negative = value < 0n
  const abs = (negative ? -value : value).toString().padStart(digits + 1, '0')
  const intPart = abs.slice(0, abs.length - digits) || '0'
  const fracPart = digits > 0 ? `.${abs.slice(abs.length - digits)}` : ''
  const grouped = intPart.replaceAll(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${fracPart}`
}

/**
 * Difference between the displayed subtotal and the sum of the displayed
 * breakdown rows, in scaled BigInt. Zero means the display rows add up.
 */
export function displayRoundingAdjustment(
  rows: readonly DisplayAmount[],
  subtotal: DisplayAmount,
  digits: number,
): bigint | null {
  let sum = BigInt(0)
  for (const row of rows) {
    const parsed = parseDisplayScaled(row.display, digits)
    if (parsed === null) return null
    sum += parsed
  }
  const subtotalParsed = parseDisplayScaled(subtotal.display, digits)
  if (subtotalParsed === null) return null
  return subtotalParsed - sum
}
