export class ApiError extends Error {
  constructor(message: string, readonly status?: number, readonly code?: string, readonly details?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
const privateKey = /token|authorization|cookie|secret|password|headers|config|request/i
function safeDetails(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeDetails)
  if (!record(value)) return value
  return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !privateKey.test(key))
    .map(([key, item]) => [key, safeDetails(item)]))
}
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (record(error)) {
    const response = record(error.response) ? error.response : null
    const body = response?.data
    const safe = safeDetails(body)
    const bodyRecord = record(safe) ? safe : null
    const code = typeof bodyRecord?.code === 'string' ? bodyRecord.code : undefined
    const status = typeof response?.status === 'number' ? response.status : undefined
    const message = typeof bodyRecord?.message === 'string' ? bodyRecord.message
      : typeof bodyRecord?.error === 'string' ? bodyRecord.error
      : typeof error.message === 'string' ? error.message : 'API request failed'
    const details = bodyRecord ? Object.fromEntries(Object.entries(bodyRecord)
      .filter(([key]) => key !== 'code' && key !== 'message' && key !== 'error')) : undefined
    return new ApiError(message, status, code, details)
  }
  return new ApiError(typeof error === 'string' ? error : 'API request failed')
}
