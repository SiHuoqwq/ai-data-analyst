import { describe, expect, it } from 'vitest'
import { AppError, normalizeError, shouldRetryQuery } from './errors'

describe('normalizeError', () => {
  it('将 FastAPI 422 detail 数组转换为可读错误', async () => {
    const response = new Response(
      JSON.stringify({ detail: [{ loc: ['body', 'file'], msg: 'Field required', type: 'missing' }] }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    )

    const error = await normalizeError(response)

    expect(error).toMatchObject({
      status: 422,
      code: 'validation_error',
      message: 'Field required',
      retryable: false,
    })
  })
})

describe('shouldRetryQuery', () => {
  it.each([400, 404, 422])('不重试 HTTP %s', (status) => {
    expect(shouldRetryQuery(0, new AppError({ status, code: 'http_error', message: '失败' }))).toBe(false)
  })

  it('网络错误和 5xx 最多重试一次', () => {
    const network = new AppError({ status: null, code: 'network_error', message: '离线', retryable: true })
    const server = new AppError({ status: 503, code: 'server_error', message: '服务异常', retryable: true })
    expect(shouldRetryQuery(0, network)).toBe(true)
    expect(shouldRetryQuery(1, network)).toBe(false)
    expect(shouldRetryQuery(0, server)).toBe(true)
    expect(shouldRetryQuery(1, server)).toBe(false)
  })
})
