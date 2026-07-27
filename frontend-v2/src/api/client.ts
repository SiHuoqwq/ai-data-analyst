import { asAppError, normalizeError } from './errors'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const TIMEOUT_MS = 12_000

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
      signal: controller.signal,
    })
    if (!response.ok) throw await normalizeError(response)
    if (response.status === 204) return undefined as T
    const text = await response.text()
    return (text ? JSON.parse(text) : undefined) as T
  } catch (error) {
    throw asAppError(error)
  } finally {
    window.clearTimeout(timeout)
  }
}
