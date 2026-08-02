// frontend/src/utils/formatUtils.js

/**
 * Format a numeric value with adaptive decimal places.
 *
 * For |value| >= 1: fixed `digits` decimal places (user's global setting).
 * For |value| < 1: show the first significant digit (e.g. 0.6803 -> "0.7",
 *   0.00011659 -> "0.0001"), clamped so a sub-1 value never rounds up across
 *   the unit boundary (0.99 -> "0.99", never "1"). Returns null for
 *   non-numeric / null input so the caller can fall back to the '–' sentinel.
 *
 * Implementation note: we use `toFixed(k)` (where k positions the decimal so the
 * first significant digit is the only one shown) plus a manual trailing-zero
 * strip, rather than `toPrecision(1)`. The naive `Number(n.toPrecision(1))`
 * approach re-introduces exponential notation for very small magnitudes
 * (e.g. 1e-7 -> "1e-7") because `Number.prototype.toString()` switches to
 * exponential below 1e-6. toFixed always renders in plain decimal form.
 *
 * @param {number|string|null} value - numeric value, or a numeric string.
 * @param {number} [digits=2] - decimal places to use when |value| >= 1.
 * @returns {string|null} Formatted string, or null for non-numeric input.
 */
export function formatQuantity(value, digits = 2) {
  if (value == null) return null
  // Treat empty string and whitespace-only strings as missing.
  if (typeof value === 'string' && value.trim() === '') return null
  const num = typeof value === 'number' ? value : parseFloat(value)
  if (Number.isNaN(num)) return null

  if (Math.abs(num) >= 1) {
    return num.toFixed(digits)
  }

  // Explicit zero guard: log10(0) is -Infinity (or null in some engines),
  // which would make the k computation below produce NaN.
  if (num === 0) {
    return '0'
  }

  // |value| < 1: position the decimal so only the first significant digit
  // survives. For 0.6803, log10(0.6803) ~= -0.167, ceil(0.167) = 1 decimal
  // place -> "0.7". For 0.00011659, log10 ~= -3.93, ceil(3.93) = 4 -> "0.0001".
  let decimals = Math.min(Math.max(Math.ceil(-Math.log10(Math.abs(num))), 0), 20)
  let s = num.toFixed(decimals)
  // Unit-boundary clamp: if rounding carried a sub-1 value up to >= 1 (e.g.
  // 0.99 -> "1.0" -> "1"), add a decimal place until the result stays < 1 in
  // magnitude, so a user holding 0.99 BTC never sees "1 BTC". Capped at 20 dp.
  while (Math.abs(parseFloat(s)) >= 1 && decimals < 20) {
    decimals += 1
    s = num.toFixed(decimals)
  }
  // Strip trailing zeros introduced by toFixed (e.g. 0.50 -> "0.5"), but keep
  // at least one fractional digit when a decimal point is present.
  if (s.indexOf('.') !== -1) {
    s = s.replace(/0+$/, '').replace(/\.$/, '')
  }
  return s
}

/**
 * Format a price with the same adaptive rule as quantities.
 *
 * Kept as a separate export so callers / templates read intent (price vs
 * quantity) even though the rule is currently identical; this also leaves room
 * to diverge the rules later (e.g. price always 2 dp) without touching the
 * template.
 *
 * @param {number|string|null} value
 * @param {number} [digits=2]
 * @returns {string|null}
 */
export function formatPrice(value, digits = 2) {
  return formatQuantity(value, digits)
}
