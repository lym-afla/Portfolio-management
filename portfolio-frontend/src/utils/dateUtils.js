import { startOfYear, parseISO, format, startOfDay } from 'date-fns'

export function calculateDateRange(value, effectiveDate) {
  const parsedEffectiveDate = parseISO(effectiveDate)
  let fromDateValue, toDateValue

  if (value === 'ytd') {
    fromDateValue = startOfYear(parsedEffectiveDate)
    toDateValue = parsedEffectiveDate
  } else if (value === 'all_time') {
    fromDateValue = null // Return null for fromDate
    toDateValue = parsedEffectiveDate
  } else {
    // Assume it's a specific year
    const year = parseInt(value, 10)
    if (isNaN(year)) {
      console.error('Invalid timespan value:', value)
      return null
    }
    fromDateValue = new Date(year, 0, 1) // January 1st of the year
    toDateValue = new Date(year, 11, 31) // December 31st of the year
  }

  return {
    fromDate: fromDateValue ? format(new Date(startOfDay(fromDateValue)), 'yyyy-MM-dd') : null,
    toDate: format(new Date(toDateValue), 'yyyy-MM-dd')
  }
}