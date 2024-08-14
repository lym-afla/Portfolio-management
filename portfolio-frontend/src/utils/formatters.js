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