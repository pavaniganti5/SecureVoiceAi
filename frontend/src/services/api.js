const STORAGE_KEY = 'securevoice_api_base_url'

export function getCustomApiBaseUrl() {
  try {
    return localStorage.getItem(STORAGE_KEY)?.trim() || ''
  } catch {
    return ''
  }
}

export function setCustomApiBaseUrl(url) {
  try {
    const trimmed = (url || '').trim()
    if (!trimmed) {
      localStorage.removeItem(STORAGE_KEY)
    } else {
      localStorage.setItem(STORAGE_KEY, trimmed)
    }
  } catch {
    // Ignore storage quota/security errors
  }
}

export function getApiBaseUrl() {
  const custom = getCustomApiBaseUrl()
  if (custom) return custom

  const configured = import.meta.env.VITE_API_BASE_URL?.trim()
  if (configured) return configured

  if (import.meta.env.DEV) return 'http://127.0.0.1:8000'
  return ''
}

export const API_BASE_URL = getApiBaseUrl()

export function apiUrl(path) {
  const base = getApiBaseUrl()
  if (!base) {
    throw new Error(
      'Backend URL is not configured. Set your Render API URL in Integration Settings or configure VITE_API_BASE_URL in Vercel.',
    )
  }
  return `${base.replace(/\/+$/, '')}${path}`
}

export function formatApiErrorMessage(error, fallbackMessage = 'Request failed') {
  if (!error) return fallbackMessage
  if (error.name === 'AbortError') return 'Request was cancelled.'

  const message = error.message || String(error)

  // Handle browser network errors ("Failed to fetch", "NetworkError", etc.)
  if (
    error instanceof TypeError &&
    (message.includes('fetch') || message.includes('Network') || message.includes('Load failed'))
  ) {
    const currentBase = getApiBaseUrl() || 'the backend service'
    return `Unable to connect to ${currentBase}. If your Render backend is hosted on a free plan, it sleeps after inactivity and takes ~50 seconds to start up. Please verify your backend URL in Settings or wait a moment for it to wake up.`
  }

  return message
}

export async function readApiResponse(response, fallbackMessage) {
  let result
  try {
    result = await response.json()
  } catch {
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new Error(
        `Backend service is unavailable or spinning up (${response.status}). Render free-tier instances may take up to a minute to start. Please try again shortly.`,
      )
    }
    if (response.status === 413) {
      throw new Error('The video file is too large for the backend limit (100 MB max).')
    }
    throw new Error(`${fallbackMessage} The backend returned an unreadable response (${response.status}).`)
  }

  if (!response.ok) {
    throw new Error(result?.detail ?? `${fallbackMessage} (${response.status}).`)
  }
  return result
}

export async function fetchAlerts({ limit = 10, offset = 0, signal } = {}) {
  try {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const response = await fetch(apiUrl(`/api/alerts?${query}`), {
      signal,
      cache: 'no-store',
    })
    return await readApiResponse(response, 'Could not load alert history')
  } catch (error) {
    throw new Error(formatApiErrorMessage(error, 'Could not load alert history'))
  }
}

export async function fetchBackendHealth(signal) {
  try {
    const response = await fetch(apiUrl('/api/health'), { signal, cache: 'no-store' })
    return await readApiResponse(response, 'Could not check backend health')
  } catch (error) {
    throw new Error(formatApiErrorMessage(error, 'Could not check backend health'))
  }
}

export async function testBackendConnection(signal) {
  const start = performance.now()
  try {
    const health = await fetchBackendHealth(signal)
    const latency = Math.round(performance.now() - start)
    return {
      connected: true,
      latencyMs: latency,
      database: health.database,
      message: `Connected successfully (${latency}ms latency). Database: ${health.database}.`,
    }
  } catch (error) {
    return {
      connected: false,
      latencyMs: null,
      database: 'disconnected',
      message: error.message,
    }
  }
}
