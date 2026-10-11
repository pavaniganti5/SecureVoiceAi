import { useCallback, useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import StatusCard from './components/StatusCard.jsx'
import CameraPanel from './components/CameraPanel.jsx'
import AlertsTable from './components/AlertsTable.jsx'
import VoiceSettings from './components/VoiceSettings.jsx'
import { Icon } from './components/Icons.jsx'
import { fetchAlerts, fetchBackendHealth } from './services/api.js'
import './App.css'

function App() {
  const [activeSection, setActiveSection] = useState('dashboard')
  const [alerts, setAlerts] = useState([])
  const [alertTotal, setAlertTotal] = useState(null)
  const [alertsLoading, setAlertsLoading] = useState(true)
  const [alertsError, setAlertsError] = useState('')
  const [health, setHealth] = useState({ state: 'checking' })
  const [voiceConfigured, setVoiceConfigured] = useState(null)
  const [currentDate] = useState(() => new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date()))

  const loadAlerts = useCallback(async (signal) => {
    try {
      const history = await fetchAlerts({ limit: 10, signal })
      setAlerts(history.items)
      setAlertTotal(history.total)
      setAlertsError('')
    } catch (error) {
      if (error.name !== 'AbortError') setAlertsError(error.message)
    } finally {
      if (!signal?.aborted) setAlertsLoading(false)
    }
  }, [])

  const refreshAlerts = useCallback(() => {
    setAlertsLoading(true)
    loadAlerts()
  }, [loadAlerts])

  const checkHealth = useCallback((signal) => {
    fetchBackendHealth(signal)
      .then((result) => {
        setHealth({
          state: 'connected',
          detail: result.database === 'connected'
            ? 'API and MongoDB connected'
            : 'API connected',
        })
      })
      .catch((error) => {
        if (!signal?.aborted && error.name !== 'AbortError') {
          setHealth({ state: 'error', detail: error.message })
        }
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetchAlerts({ limit: 10, signal: controller.signal })
      .then((history) => {
        if (controller.signal.aborted) return
        setAlerts(history.items)
        setAlertTotal(history.total)
      })
      .catch((error) => {
        if (!controller.signal.aborted && error.name !== 'AbortError') {
          setAlertsError(error.message)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setAlertsLoading(false)
      })
    checkHealth(controller.signal)
    return () => controller.abort()
  }, [loadAlerts, checkHealth])

  const navigateTo = (section) => {
    setActiveSection(section)
    document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const detectedRecently = alerts.filter((alert) => alert.detection_status === 'detected').length

  return (
    <div className="app-shell">
      <Sidebar activeSection={activeSection} onNavigate={navigateTo} />

      <main className="main-content">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark"><Icon name="brand" /></span>
            <span>SecureVoice <strong>AI</strong></span>
          </div>
          <div className="breadcrumb">Workspace <span>/</span> <strong>Overview</strong></div>
          <div className="topbar-right">
            <span className="date-label"><Icon name="calendar" /> {currentDate}</span>
            <span className={`system-pill ${health.state}`}>
              <span /> {health.state === 'connected' ? 'System online' : health.state === 'checking' ? 'Checking system' : 'System unavailable'}
            </span>
          </div>
        </header>

        <div className="page-content">
          <section id="dashboard" className="welcome-row">
            <div>
              <p className="eyebrow">HOME SECURITY WORKSPACE</p>
              <h1>Good overview. Clear next steps.</h1>
              <p className="welcome-copy">Review real detection activity and run a local video analysis.</p>
            </div>
            <span className="privacy-badge"><Icon name="shield" /> Privacy-first processing</span>
          </section>

          <div className="prototype-notice" role="note">
            <Icon name="info" />
            <p><strong>Prototype safety note.</strong> Video detection runs on the backend and uploaded clips are temporary. Live webcam monitoring is not connected. This application detects observable person-entry events only and is not a substitute for a professional security system.</p>
          </div>

          <section className="status-grid" aria-label="System overview">
            <StatusCard
              label="System health"
              value={health.state === 'connected' ? 'Connected' : health.state === 'checking' ? 'Checking' : 'Unavailable'}
              detail={health.detail ?? 'Checking API and database'}
              icon="pulse"
              tone={health.state === 'connected' ? 'green' : health.state === 'error' ? 'red' : 'blue'}
              marker={health.state === 'connected' ? 'online' : health.state === 'error' ? 'critical' : 'pending'}
            />
            <StatusCard
              label="Total alerts"
              value={alertTotal === null ? '—' : String(alertTotal)}
              detail={alertsError ? 'Alert history unavailable' : 'Saved in MongoDB history'}
              icon="bell"
              tone="blue"
            />
            <StatusCard
              label="Recent detections"
              value={alertsLoading && alerts.length === 0 ? '—' : String(detectedRecently)}
              detail="Among the 10 most recent alerts"
              icon="camera"
              tone="teal"
            />
            <StatusCard
              label="Voice alerts"
              value={voiceConfigured === null ? 'Checking' : voiceConfigured ? 'Configured' : 'Not configured'}
              detail="Murf status only · credentials stay private"
              icon="volume"
              tone={voiceConfigured ? 'green' : 'amber'}
            />
          </section>

          <section id="video-analysis" className="panel video-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">BACKEND COMPUTER VISION</p>
                <h2>Video analysis</h2>
                <p className="section-description">Upload a short clip to detect people entering the monitored region.</p>
              </div>
              <span className="feature-tag"><span className="tag-dot" /> Available</span>
            </div>
            <CameraPanel onAnalysisComplete={refreshAlerts} />
          </section>

          <section id="monitoring" className="panel unavailable-panel">
            <div className="unavailable-icon"><Icon name="camera" /></div>
            <div className="unavailable-copy">
              <p className="eyebrow">CAMERA MODE</p>
              <h2>Live monitoring is not connected</h2>
              <p className="section-description">This build does not request camera access or stream webcam frames. Use Video analysis to analyze a clip. Live monitoring will be listed as available only after it is implemented and browser-tested.</p>
            </div>
            <span className="feature-tag neutral-tag">Not connected</span>
          </section>

          <section id="history" className="panel alerts-panel">
            <div className="panel-heading alerts-heading">
              <div>
                <p className="eyebrow">MONGODB · LIVE API DATA</p>
                <h2>Recent security alerts</h2>
                <p className="section-description">Latest saved events, ordered newest first.</p>
              </div>
            </div>
            <AlertsTable alerts={alerts} error={alertsError} isLoading={alertsLoading} onRefresh={refreshAlerts} />
          </section>

          <section id="settings" className="panel settings-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">INTEGRATION SETTINGS</p>
                <h2>Voice alerts</h2>
                <p className="section-description">Check service availability without exposing credentials.</p>
              </div>
              <span className="icon-tile teal"><Icon name="volume" /></span>
            </div>
            <VoiceSettings
              onStatusChange={setVoiceConfigured}
              onBackendChange={() => {
                refreshAlerts()
                checkHealth()
              }}
            />
          </section>

          <footer className="page-footer">
            <span><Icon name="brand" /> SecureVoice AI <span className="footer-version">· Safety prototype</span></span>
            <span>Not a substitute for a professional security system.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

export default App
