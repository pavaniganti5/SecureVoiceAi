import { useCallback, useEffect, useState } from 'react'
import { getVoiceStatus } from '../services/voice.js'
import {
  getApiBaseUrl,
  getCustomApiBaseUrl,
  setCustomApiBaseUrl,
  testBackendConnection,
} from '../services/api.js'
import { Icon } from './Icons.jsx'

function VoiceSettings({ onStatusChange, onBackendChange }) {
  const [status, setStatus] = useState({ state: 'checking' })
  const [backendUrl, setBackendUrl] = useState(() => getCustomApiBaseUrl() || getApiBaseUrl())
  const [isEditingUrl, setIsEditingUrl] = useState(false)
  const [tempUrl, setTempUrl] = useState(() => getCustomApiBaseUrl() || getApiBaseUrl())
  const [testResult, setTestResult] = useState(null)
  const [isTesting, setIsTesting] = useState(false)

  const checkVoice = useCallback((signal) => {
    getVoiceStatus(signal)
      .then((result) => {
        setStatus({ state: 'ready', ...result })
        onStatusChange?.(result.configured)
      })
      .catch((error) => {
        if (!signal?.aborted && error.name !== 'AbortError') {
          setStatus({ state: 'error', message: error.message })
          onStatusChange?.(false)
        }
      })
  }, [onStatusChange])

  useEffect(() => {
    const controller = new AbortController()
    checkVoice(controller.signal)
    return () => controller.abort()
  }, [backendUrl, checkVoice])

  const handleSaveUrl = (e) => {
    e.preventDefault()
    setCustomApiBaseUrl(tempUrl)
    setBackendUrl(getApiBaseUrl())
    setIsEditingUrl(false)
    setTestResult(null)
    onBackendChange?.()
  }

  const handleResetUrl = () => {
    setCustomApiBaseUrl('')
    const defaultUrl = getApiBaseUrl()
    setTempUrl(defaultUrl)
    setBackendUrl(defaultUrl)
    setIsEditingUrl(false)
    setTestResult(null)
    onBackendChange?.()
  }

  const handleTestConnection = async () => {
    setIsTesting(true)
    setTestResult(null)
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 65000)

    try {
      const result = await testBackendConnection(controller.signal)
      setTestResult(result)
      if (result.connected) {
        checkVoice()
        onBackendChange?.()
      }
    } finally {
      clearTimeout(timer)
      setIsTesting(false)
    }
  }

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
        <div className="setting-row backend-setting-row">
          <div className="backend-setting-info">
            <div className="setting-name">Backend API Server (Render)</div>
            <p className="setting-description">
              Endpoint: <code>{backendUrl || 'None configured (Set below)'}</code>
            </p>
            {isEditingUrl ? (
              <form className="backend-url-form" onSubmit={handleSaveUrl}>
                <input
                  aria-label="Backend API Base URL"
                  className="backend-url-input"
                  onChange={(e) => setTempUrl(e.target.value)}
                  placeholder="https://your-service.onrender.com"
                  type="url"
                  value={tempUrl}
                />
                <div className="url-form-buttons">
                  <button className="button button-primary" type="submit">
                    Save URL
                  </button>
                  <button
                    className="button button-secondary"
                    onClick={() => {
                      setTempUrl(backendUrl)
                      setIsEditingUrl(false)
                    }}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button
                    className="button button-ghost"
                    onClick={handleResetUrl}
                    title="Reset to build environment default"
                    type="button"
                  >
                    Reset default
                  </button>
                </div>
              </form>
            ) : (
              <div className="backend-action-buttons">
                <button
                  className="button button-secondary button-sm"
                  onClick={() => setIsEditingUrl(true)}
                  type="button"
                >
                  <Icon name="settings" /> Configure URL
                </button>
                <button
                  className="button button-primary button-sm"
                  disabled={isTesting}
                  onClick={handleTestConnection}
                  type="button"
                >
                  <Icon name="pulse" /> {isTesting ? 'Waking backend (up to 50s)…' : 'Test & Wake Backend'}
                </button>
              </div>
            )}
            {testResult && (
              <div className={`connection-test-result ${testResult.connected ? 'connected' : 'failed'}`}>
                <span className="test-status-dot" />
                <span>{testResult.message}</span>
              </div>
            )}
          </div>
          <span className={`integration-status ${testResult?.connected ? 'configured' : ''}`}>
            <span /> {testResult?.connected ? 'Online' : 'Configured'}
          </span>
        </div>

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
      <p className="settings-footnote">
        Render free-tier web services spin down after 15 minutes of inactivity and take ~50 seconds to wake on the first request. Use &quot;Test &amp; Wake Backend&quot; to warm up the service before running video analysis.
      </p>
    </>
  )
}

export default VoiceSettings
