import { apiUrl, readApiResponse } from './api.js'

export async function analyzeVideo(file, settings, analysisId, signal) {
  const body = new FormData()
  body.append('video', file)

  for (const [key, value] of Object.entries(settings)) {
    body.append(key, String(value))
  }

  const response = await fetch(apiUrl('/api/detection/video'), {
    method: 'POST',
    body,
    headers: { 'X-Analysis-ID': analysisId },
    signal,
  })
  return readApiResponse(response, 'Video analysis failed')
}

export async function cancelVideoAnalysis(analysisId) {
  const response = await fetch(
    apiUrl(`/api/detection/cancel/${analysisId}`),
    { method: 'POST' },
  )
  if (!response.ok && response.status !== 404) {
    throw new Error('The backend could not stop this video analysis.')
  }
}
