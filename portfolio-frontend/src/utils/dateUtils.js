import { startOfYear, parseISO, format, startOfDay } from 'date-fns'

export function calculateDateRange(value, effectiveDate) {
  const parsedEffectiveDate = parseISO(effectiveDate)
  let dateFromValue, dateToValue

  if (value === 'ytd') {
    dateFromValue = startOfYear(parsedEffectiveDate)
    dateToValue = parsedEffectiveDate
  } else if (value === 'all_time') {
    dateFromValue = null // Return null for dateFrom
    dateToValue = parsedEffectiveDate
  } else {
    // Assume it's a specific year
    const year = parseInt(value, 10)
    if (isNaN(year)) {
      console.error('Invalid timespan value:', value)
      return null
    }
    dateFromValue = new Date(year, 0, 1) // January 1st of the year
    dateToValue = new Date(year, 11, 31) // December 31st of the year
  }

  return {
    dateFrom: dateFromValue ? format(new Date(startOfDay(dateFromValue)), 'yyyy-MM-dd') : null,
    dateTo: format(new Date(dateToValue), 'yyyy-MM-dd')
  }
}