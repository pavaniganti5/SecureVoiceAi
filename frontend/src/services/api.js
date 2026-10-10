const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
export const API_BASE_URL = configuredApiBaseUrl || (
  import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
)

export function apiUrl(path) {
  if (!API_BASE_URL) {
    throw new Error('Backend URL is not configured. Set VITE_API_BASE_URL and rebuild the frontend.')
  }
  return `${API_BASE_URL.replace(/\/+$/, '')}${path}`
}

export async function readApiResponse(response, fallbackMessage) {
  let result
  try {
    result = await response.json()
  } catch {
    throw new Error(`${fallbackMessage} The backend returned an unreadable response.`)
  }

  if (!response.ok) {
    throw new Error(result.detail ?? `${fallbackMessage} (${response.status}).`)
  }
  return result
}

export async function fetchAlerts({ limit = 10, offset = 0, signal } = {}) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const response = await fetch(apiUrl(`/api/alerts?${query}`), {
    signal,
    cache: 'no-store',
  })
  return readApiResponse(response, 'Could not load alert history')
}

export async function fetchBackendHealth(signal) {
  const response = await fetch(apiUrl('/api/health'), { signal, cache: 'no-store' })
  return readApiResponse(response, 'Could not check backend health')
}
