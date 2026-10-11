import { apiUrl, formatApiErrorMessage, readApiResponse } from './api.js'

export async function analyzeVideo(file, settings, analysisId, signal) {
  const body = new FormData()
  body.append('video', file)

  for (const [key, value] of Object.entries(settings)) {
    body.append(key, String(value))
  }

  try {
    const response = await fetch(apiUrl('/api/detection/video'), {
      method: 'POST',
      body,
      headers: { 'X-Analysis-ID': analysisId },
      signal,
    })
    return await readApiResponse(response, 'Video analysis failed')
  } catch (error) {
    throw new Error(formatApiErrorMessage(error, 'Video analysis failed'))
  }
}

export async function cancelVideoAnalysis(analysisId) {
  try {
    const response = await fetch(
      apiUrl(`/api/detection/cancel/${analysisId}`),
      { method: 'POST' },
    )
    if (!response.ok && response.status !== 404) {
      throw new Error('The backend could not stop this video analysis.')
    }
  } catch (error) {
    throw new Error(formatApiErrorMessage(error, 'Failed to stop video analysis'))
  }
}

export async function loadDemoVideo(signal) {
  // Try static client asset first (immediate, no cold start), then fall back to backend endpoint
  const candidates = [
    '/demo-security-video.mp4',
    apiUrl('/api/detection/sample-video'),
  ]

  let lastError = null
  for (const url of candidates) {
    try {
      const response = await fetch(url, { signal })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const blob = await response.blob()
      return new File([blob], 'demo-security-video.mp4', {
        type: 'video/mp4',
        lastModified: Date.now(),
      })
    } catch (err) {
      lastError = err
    }
  }

  throw new Error(
    formatApiErrorMessage(
      lastError,
      'Could not load the built-in demo video. Check network connection.',
    ),
  )
}
