import { useEffect, useMemo, useRef, useState } from 'react'
import { analyzeVideo, cancelVideoAnalysis, loadDemoVideo } from '../services/detection.js'
import { updatePlaybackStatus } from '../services/voice.js'
import { Icon } from './Icons.jsx'

const MAX_VIDEO_BYTES = 100 * 1024 * 1024
const initialRoi = { roi_x: 0, roi_y: 0, roi_width: 1, roi_height: 1 }

function CameraPanel({ onAnalysisComplete }) {
  const [video, setVideo] = useState(null)
  const [previewMode, setPreviewMode] = useState('annotated')
  const [isDemoVideo, setIsDemoVideo] = useState(false)
  const [isLoadingDemo, setIsLoadingDemo] = useState(false)
  const [confidence, setConfidence] = useState(0.35)
  const [cooldown, setCooldown] = useState(10)
  const [inferenceFps, setInferenceFps] = useState(2)
  const [roi, setRoi] = useState(initialRoi)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [playingEventId, setPlayingEventId] = useState(null)
  const [playbackMessages, setPlaybackMessages] = useState({})
  const abortController = useRef(null)
  const analysisIdRef = useRef(null)
  const audioRef = useRef(null)

  const videoPreviewUrl = useMemo(() => {
    return video ? URL.createObjectURL(video) : null
  }, [video])

  useEffect(() => {
    return () => {
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl)
    }
  }, [videoPreviewUrl])

  const selectFile = (file, isDemo = false) => {
    setResult(null)
    setError('')
    setIsDemoVideo(isDemo)

    if (file && file.size > MAX_VIDEO_BYTES) {
      setVideo(null)
      setError('Choose a video smaller than 100 MB.')
      return
    }

    if (file && !/\.(mp4|mov|avi|mkv|webm)$/i.test(file.name)) {
      setVideo(null)
      setError('Choose an MP4, MOV, AVI, MKV, or WebM video.')
      return
    }

    setVideo(file)
    setPreviewMode('video')
  }

  const selectVideo = (event) => {
    selectFile(event.target.files?.[0] ?? null, false)
    event.target.value = ''
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)
    selectFile(event.dataTransfer.files?.[0] ?? null, false)
  }

  const handleLoadDemo = async () => {
    setError('')
    setResult(null)
    setIsLoadingDemo(true)
    try {
      const demoFile = await loadDemoVideo()
      selectFile(demoFile, true)
    } catch (demoError) {
      setError(demoError.message)
    } finally {
      setIsLoadingDemo(false)
    }
  }

  const updateRoi = (key, value) => {
    setRoi((current) => ({ ...current, [key]: Number(value) }))
  }

  const startAnalysis = async () => {
    if (!video) {
      setError('Select a video file or load the sample demo video first.')
      return
    }

    setError('')
    setResult(null)
    setIsAnalyzing(true)
    const controller = new AbortController()
    const analysisId = crypto.randomUUID()
    abortController.current = controller
    analysisIdRef.current = analysisId

    try {
      const analysis = await analyzeVideo(
        video,
        {
          confidence,
          cooldown_seconds: cooldown,
          inference_fps: inferenceFps,
          ...roi,
        },
        analysisId,
        controller.signal,
      )
      setResult(analysis)
      setPreviewMode('annotated')
      onAnalysisComplete?.()
    } catch (analysisError) {
      setError(
        analysisError.name === 'AbortError'
          ? 'Video analysis was stopped.'
          : analysisError.message,
      )
    } finally {
      abortController.current = null
      analysisIdRef.current = null
      setIsAnalyzing(false)
    }
  }

  const stopAnalysis = async () => {
    if (!analysisIdRef.current) return
    try {
      await cancelVideoAnalysis(analysisIdRef.current)
    } catch (cancelError) {
      setError(cancelError.message)
    } finally {
      abortController.current?.abort()
    }
  }

  const playAlertAudio = async (event) => {
    if (!event.audio_base64 || !event.audio_content_type) return
    audioRef.current?.pause()
    const audio = new Audio(
      `data:${event.audio_content_type};base64,${event.audio_base64}`,
    )
    audioRef.current = audio
    setPlayingEventId(event.event_id)
    setPlaybackMessages((current) => ({ ...current, [event.event_id]: '' }))
    audio.onended = () => setPlayingEventId(null)

    try {
      await audio.play()
      try {
        await updatePlaybackStatus(event.event_id, 'played')
        setPlaybackMessages((current) => ({ ...current, [event.event_id]: 'Played' }))
      } catch (statusError) {
        setPlaybackMessages((current) => ({
          ...current,
          [event.event_id]: `Audio played; history update failed: ${statusError.message}`,
        }))
      }
    } catch {
      setPlayingEventId(null)
      try {
        await updatePlaybackStatus(event.event_id, 'failed')
      } catch (statusError) {
        setPlaybackMessages((current) => ({
          ...current,
          [event.event_id]: `Playback failed; history update failed: ${statusError.message}`,
        }))
        return
      }
      setPlaybackMessages((current) => ({
        ...current,
        [event.event_id]: 'Playback failed. Check your browser audio settings and try again.',
      }))
    }
  }

  const scrollToSettings = () => {
    document.getElementById('settings')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <>
      <div className="demo-banner">
        <div className="demo-banner-content">
          <div className="demo-banner-tag">
            <span className="demo-chip-badge">SAMPLE VIDEO READY</span>
            <strong>Pedestrian Walk-in Security Demo</strong>
          </div>
          <p className="demo-banner-desc">
            A 10-second high-efficiency surveillance clip (H.264 MP4) with pedestrian entry is bundled directly in this project.
          </p>
        </div>
        <div className="demo-banner-actions">
          <button
            className="button button-primary demo-btn"
            disabled={isLoadingDemo || isAnalyzing}
            onClick={handleLoadDemo}
            type="button"
          >
            <Icon name="play" /> {isLoadingDemo ? 'Loading demo clip…' : 'Load Sample Video'}
          </button>
          <a
            className="button button-ghost demo-download-link"
            download="demo-security-video.mp4"
            href="/demo-security-video.mp4"
            title="Download demo video to local drive"
          >
            <Icon name="download" /> Download Clip
          </a>
        </div>
      </div>

      <div className="camera-preview" aria-live="polite">
        {result?.annotated_frame_jpeg ? (
          <div className="preview-wrapper">
            <div className="preview-mode-switch">
              <button
                className={`mode-switch-btn ${previewMode === 'annotated' ? 'active' : ''}`}
                onClick={() => setPreviewMode('annotated')}
                type="button"
              >
                Annotated Frame ({result.person_detections} detections)
              </button>
              {videoPreviewUrl && (
                <button
                  className={`mode-switch-btn ${previewMode === 'video' ? 'active' : ''}`}
                  onClick={() => setPreviewMode('video')}
                  type="button"
                >
                  Source Video
                </button>
              )}
            </div>
            {previewMode === 'annotated' ? (
              <img
                className="analysis-preview"
                src={`data:image/jpeg;base64,${result.annotated_frame_jpeg}`}
                alt="Annotated frame showing detected people and the monitored region"
              />
            ) : (
              <video
                className="analysis-video-player"
                controls
                playsInline
                preload="metadata"
                src={videoPreviewUrl}
              >
                <track kind="captions" />
              </video>
            )}
          </div>
        ) : videoPreviewUrl ? (
          <div className="preview-wrapper">
            <div className="preview-badge-overlay">
              <span>{isDemoVideo ? 'Sample Video Loaded' : 'Custom Video Ready'}</span>
            </div>
            <video
              className="analysis-video-player"
              controls
              playsInline
              preload="metadata"
              src={videoPreviewUrl}
            >
              <track kind="captions" />
            </video>
          </div>
        ) : (
          <div className="preview-empty">
            <span className="preview-camera-icon"><Icon name="camera" /></span>
            <strong>{isAnalyzing ? 'Analyzing video on backend…' : 'No video selected'}</strong>
            <p>
              {isAnalyzing
                ? 'YOLO person detection is running on your configured backend. Please keep this page open.'
                : 'Click "Load Sample Video" above or choose a local clip to see person boxes and region entry alerts.'}
            </p>
            {!isAnalyzing && (
              <div className="empty-quick-action">
                <button
                  className="button button-secondary quick-demo-btn"
                  disabled={isLoadingDemo}
                  onClick={handleLoadDemo}
                  type="button"
                >
                  <Icon name="play" /> Load Sample Video
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <label
        className={`upload-dropzone${isDragging ? ' dragging' : ''}`}
        htmlFor="security-video"
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true) }}
        onDragLeave={(event) => { event.preventDefault(); setIsDragging(false) }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        <input
          accept=".mp4,.mov,.avi,.mkv,.webm,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm"
          className="upload-input"
          id="security-video"
          onChange={selectVideo}
          type="file"
        />
        <span className="upload-icon"><Icon name="upload" /></span>
        <span className="upload-copy">
          <strong>
            {video ? video.name : 'Drop a video here or browse files'}
            {isDemoVideo && <span className="demo-pill">Sample demo</span>}
          </strong>
          <small>
            {video
              ? `${(video.size / 1024 / 1024).toFixed(2)} MB selected · Ready to analyze`
              : 'MP4, MOV, AVI, MKV, or WebM · up to 100 MB · 2 minutes'}
          </small>
        </span>
        <span className="upload-browse">Browse file</span>
      </label>

      {isAnalyzing && (
        <div className="analysis-progress-container">
          <div className="analysis-progress" role="progressbar" aria-label="Video analysis in progress">
            <span />
          </div>
          <div className="analysis-status-hint">
            <span>Analyzing video frames with AI & syncing alert audio…</span>
          </div>
        </div>
      )}

      <div className="video-controls">
        <div className="video-file-note">
          {video
            ? `Ready: ${video.name} (${(video.size / 1024 / 1024).toFixed(2)} MB). Uploaded frames are processed temporarily and not stored.`
            : 'Select a clip or click Load Sample Video to run person detection through the backend API.'}
        </div>
      </div>

      <details className="detection-settings">
        <summary>Detection settings</summary>
        <div className="detection-settings-grid">
          <label>
            Confidence threshold <strong>{Number(confidence).toFixed(2)}</strong>
            <input
              max="1"
              min="0.1"
              onChange={(event) => setConfidence(Number(event.target.value))}
              step="0.05"
              type="range"
              value={confidence}
            />
          </label>
          <label>
            Event cooldown
            <select onChange={(event) => setCooldown(Number(event.target.value))} value={cooldown}>
              <option value="0">No cooldown</option>
              <option value="5">5 seconds</option>
              <option value="10">10 seconds</option>
              <option value="30">30 seconds</option>
              <option value="60">60 seconds</option>
            </select>
          </label>
          <label>
            Inference sampling
            <select
              onChange={(event) => setInferenceFps(Number(event.target.value))}
              value={inferenceFps}
            >
              <option value="1">1 frame/second · fastest</option>
              <option value="2">2 frames/second · balanced (recommended)</option>
              <option value="5">5 frames/second · high detail (slower)</option>
              <option value="10">10 frames/second · maximum detail (slowest)</option>
            </select>
          </label>
          <div className="roi-controls">
            <span>Monitored region <small>(normalized 0–1)</small></span>
            {[
              ['roi_x', 'Left (X)'],
              ['roi_y', 'Top (Y)'],
              ['roi_width', 'Width'],
              ['roi_height', 'Height'],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  max="1"
                  min={key === 'roi_width' || key === 'roi_height' ? '0.05' : '0'}
                  onChange={(event) => updateRoi(key, event.target.value)}
                  step="0.05"
                  type="number"
                  value={roi[key]}
                />
              </label>
            ))}
          </div>
          <p className="roi-help">A detection enters the region when the center of its person bounding box falls inside it.</p>
        </div>
      </details>

      {error && (
        <div className="detection-error-card" role="alert">
          <div className="error-card-header">
            <strong>Analysis error</strong>
            <span className="error-card-badge">Connection / Processing issue</span>
          </div>
          <p className="error-card-message">{error}</p>
          <div className="error-card-actions">
            <button
              className="button button-primary retry-btn"
              disabled={!video || isAnalyzing}
              onClick={startAnalysis}
              type="button"
            >
              <Icon name="refresh" /> Retry analysis
            </button>
            <button
              className="button button-ghost settings-hint-btn"
              onClick={scrollToSettings}
              type="button"
            >
              <Icon name="settings" /> Check backend connection
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="analysis-result" role="status">
          <div className="analysis-metrics">
            <span><strong>{result.person_detections}</strong> person boxes</span>
            <span><strong>{result.region_entry_events.length}</strong> region entries</span>
            <span><strong>{result.duration_seconds}s</strong> clip analyzed</span>
            {result.processing_time_seconds != null && (
              <span>
                <strong>{result.processing_time_seconds.toFixed(2)}s</strong> processing time
              </span>
            )}
          </div>
          {result.region_entry_events.length > 0 ? (
            <ul className="detection-events">
              {result.region_entry_events.map((event) => (
                <li key={event.event_id}>
                  <div className="detection-event-heading">
                    <span>Person entered at {event.media_time_seconds}s · confidence {event.confidence.toFixed(2)}</span>
                    <span className={`voice-event-status ${event.voice_generation_status}`}>
                      {event.voice_generation_status === 'generated' ? 'Murf audio ready' : 'Voice unavailable'}
                    </span>
                  </div>
                  <p className="detection-alert-message">{event.alert_message}</p>
                  {event.audio_base64 && (
                    <button
                      className="button button-secondary play-alert-button"
                      disabled={playingEventId === event.event_id}
                      onClick={() => playAlertAudio(event)}
                      type="button"
                    >
                      <Icon name="play" />
                      {playingEventId === event.event_id ? 'Playing…' : 'Play voice alert'}
                    </button>
                  )}
                  {event.voice_error && <p className="voice-error-detail">{event.voice_error}</p>}
                  {playbackMessages[event.event_id] && (
                    <p className="playback-status" role="status">{playbackMessages[event.event_id]}</p>
                  )}
                  <span className="event-history-id">Alert history #{event.event_id}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="no-entry-note">No person entry into the monitored region was detected in this clip.</p>
          )}
          <p className="no-entry-note">This detects people and movement events only; it does not identify individuals or determine intent. The uploaded clip was not saved.</p>
        </div>
      )}

      <div className="camera-controls">
        <span className="camera-source">
          <Icon name="camera" />
          {video ? (isDemoVideo ? 'Sample demo video loaded' : 'Local video clip loaded') : 'No clip loaded'}
        </span>
        <div className="button-group">
          <button
            className="button button-primary"
            disabled={!video || isAnalyzing}
            onClick={startAnalysis}
            type="button"
          >
            <Icon name="play" /> {isAnalyzing ? 'Analyzing…' : 'Start analysis'}
          </button>
          <button
            className="button button-secondary"
            disabled={!isAnalyzing}
            onClick={stopAnalysis}
            type="button"
          >
            <Icon name="stop" /> Stop
          </button>
        </div>
      </div>
    </>
  )
}

export default CameraPanel
