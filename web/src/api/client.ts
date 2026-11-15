interface RuntimeConfig {
  OPPORTUNITY_API_BASE?: string
  OPPORTUNITY_DESKTOP_TOKEN?: string
}

const runtime = window as typeof window & RuntimeConfig

export const API_BASE = (runtime.OPPORTUNITY_API_BASE || '/api/v1').replace(
  /\/+$/,
  '',
)

export const DESKTOP_TOKEN = runtime.OPPORTUNITY_DESKTOP_TOKEN || null

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter((item): item is string => Boolean(item))
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return fallback
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  timeoutMs?: number
  token?: string | null
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, timeoutMs = 30_000, token } = options
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['X-Opportunity-Token'] = token

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
    const text = await response.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = text
      }
    }
    if (!response.ok) {
      const detail =
        data && typeof data === 'object' && 'detail' in data
          ? (data as { detail: unknown }).detail
          : data
      throw new ApiError(
        formatDetail(detail, `请求失败（HTTP ${response.status}）`),
        response.status,
      )
    }
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(
        '请求超时。后端可能仍在运行，请稍后到「采集历史」查看结果。',
        0,
      )
    }
    throw new ApiError(
      '无法连接本地 API。请确认后端已启动，或点击顶部状态重试。',
      0,
    )
  } finally {
    window.clearTimeout(timer)
  }
}
