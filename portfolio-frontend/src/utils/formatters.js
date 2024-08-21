import { format, parseISO } from 'date-fns'

export const formatDate = (dateString) => {
  if (!dateString) return ''
  try {
    return format(parseISO(dateString), 'd-MMM-yy')
  } catch (error) {
    console.error('Error formatting date:', error)
    return dateString
  }
}

// export const formatDatePicker = (date) => {
//   if (!date) return ''
//   try {
//     const d = new Date(date)
//     return format(d, 'yyyy-MM-dd')
//   } catch (error) {
//     console.error('Error formatting date picker value:', error)
//     return ''
//   }
// }

// export const parseDateString = (dateString) => {
//   if (!dateString) return null
//   const parsedDate = parseISO(dateString, 'dd-MMM-yy')
//   return isValid(parsedDate) ? parsedDate : null
// }