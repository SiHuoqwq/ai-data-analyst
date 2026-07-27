export interface AppErrorInit {
  status: number | null
  code: string
  message: string
  detail?: unknown
  retryable?: boolean
}

export class AppError extends Error {
  readonly status: number | null
  readonly code: string
  readonly detail?: unknown
  readonly retryable: boolean

  constructor({ status, code, message, detail, retryable = false }: AppErrorInit) {
    super(message)
    this.name = 'AppError'
    this.status = status
    this.code = code
    this.detail = detail
    this.retryable = retryable
  }
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : null))
      .filter(Boolean)
    return messages.length ? messages.join('；') : null
  }
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  return null
}

export async function normalizeError(response: Response): Promise<AppError> {
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload
  const status = response.status
  const code = status === 422 ? 'validation_error' : status >= 500 ? 'server_error' : status === 404 ? 'not_found' : 'http_error'
  const fallback = status === 404 ? '请求的内容不存在' : status >= 500 ? '服务器暂时不可用' : '请求未能完成'
  return new AppError({ status, code, message: detailMessage(detail) || fallback, detail, retryable: status >= 500 })
}

export function asAppError(error: unknown): AppError {
  if (error instanceof AppError) return error
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new AppError({ status: null, code: 'timeout', message: '请求超时，请稍后重试', retryable: true })
  }
  return new AppError({ status: null, code: 'network_error', message: '无法连接后端，请检查服务是否启动', detail: error, retryable: true })
}

export function shouldRetryQuery(failureCount: number, error: Error): boolean {
  const appError = asAppError(error)
  return appError.retryable && failureCount < 1
}
