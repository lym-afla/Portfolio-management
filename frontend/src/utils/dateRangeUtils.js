import {
  parseISO,
  startOfYear,
  subMonths,
  subYears,
  startOfDay,
  format,
} from 'date-fns'

export function calculateDateRange(
  value,
  effectiveCurrentDate,
  customFrom = null,
  customTo = null
) {
  const effectiveDate = parseISO(effectiveCurrentDate)
  let fromDate = null
  let toDate = effectiveDate

  switch (value) {
    case 'ytd':
      fromDate = startOfYear(effectiveDate)
      break
    case 'last1m':
      fromDate = subMonths(effectiveDate, 1)
      break
    case 'last3m':
      fromDate = subMonths(effectiveDate, 3)
      break
    case 'last6m':
      fromDate = subMonths(effectiveDate, 6)
      break
    case 'last12m':
      fromDate = subMonths(effectiveDate, 12)
      break
    case 'last3y':
      fromDate = subYears(effectiveDate, 3)
      break
    case 'last5y':
      fromDate = subYears(effectiveDate, 5)
      break
    case 'all_time':
      fromDate = null
      break
    case 'custom': {
      // The valuation date bounds the charted range: persisted custom bounds
      // later than the committed effective date clamp to it (From included,
      // otherwise the range would start after the whole valuation window).
      const customToDate = customTo && parseISO(customTo) < effectiveDate ? parseISO(customTo) : effectiveDate
      const customFromDate = customFrom && parseISO(customFrom) < effectiveDate ? parseISO(customFrom) : effectiveDate
      fromDate = customFromDate
      toDate = customToDate
      break
    }
  }

  return {
    from: fromDate ? format(startOfDay(fromDate), 'yyyy-MM-dd') : null,
    to: format(toDate, 'yyyy-MM-dd'),
  }
}
