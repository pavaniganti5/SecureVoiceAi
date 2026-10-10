import { apiUrl, readApiResponse } from './api.js'

export async function getVoiceStatus(signal) {
  const response = await fetch(apiUrl('/api/voice/status'), { signal })
  return readApiResponse(response, 'Could not read voice service status')
}

export async function updatePlaybackStatus(eventId, status) {
  const response = await fetch(apiUrl(`/api/alerts/${encodeURIComponent(eventId)}/playback`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  return readApiResponse(response, 'Could not update the audio playback status')
}
