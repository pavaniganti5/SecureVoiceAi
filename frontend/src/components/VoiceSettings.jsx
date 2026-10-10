import { useEffect, useState } from 'react'
import { getVoiceStatus } from '../services/voice.js'

function VoiceSettings({ onStatusChange }) {
  const [status, setStatus] = useState({ state: 'checking' })

  useEffect(() => {
    const controller = new AbortController()
    getVoiceStatus(controller.signal)
      .then((result) => {
        setStatus({ state: 'ready', ...result })
        onStatusChange?.(result.configured)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setStatus({ state: 'error', message: error.message })
          onStatusChange?.(false)
        }
      })
    return () => controller.abort()
  }, [onStatusChange])

  const integrationLabel = {
    checking: 'Checking…',
    ready: status.configured ? 'Configured' : 'API key missing',
    error: 'Backend unavailable',
  }[status.state]

  const description = {
    checking: 'Checking backend voice settings',
    ready: status.configured
      ? `Murf ${status.model} · ${status.voice_id}`
      : 'Add MURF_API_KEY to backend/.env',
    error: status.message,
  }[status.state]

  return (
    <>
      <div className="settings-list">
        <div className="setting-row">
          <div>
            <div className="setting-name">Murf AI connection</div>
            <p className="setting-description">{description}</p>
          </div>
          <span className={`integration-status ${status.configured ? 'configured' : ''}`}>
            <span /> {integrationLabel}
          </span>
        </div>
        <div className="setting-row">
          <div>
            <div className="setting-name">Speech generation</div>
            <p className="setting-description">MP3 audio · generated for region-entry events</p>
          </div>
          <span className="voice-model-label">{status.voice_id ?? 'GEN2'}</span>
        </div>
      </div>
      <p className="settings-footnote">Only alert text is sent to Murf. The API key stays in the backend; generated audio is returned to this page and is not stored by this app. Murf usage may incur charges.</p>
    </>
  )
}

export default VoiceSettings
