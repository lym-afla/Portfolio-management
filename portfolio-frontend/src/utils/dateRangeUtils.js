import { parseISO, startOfYear, subMonths, subYears, startOfDay, format } from 'date-fns'

export function calculateDateRange(value, effectiveCurrentDate) {
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
  }
  
  return {
    from: fromDate ? format(startOfDay(fromDate), 'yyyy-MM-dd') : null,
    to: format(toDate, 'yyyy-MM-dd')
  }
}