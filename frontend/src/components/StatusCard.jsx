import { Icon } from './Icons.jsx'

function StatusCard({ label, value, detail, icon, tone, marker, compact = false }) {
  return (
    <article className="status-card">
      <div className="status-card-top">
        <span className="status-label">{label}</span>
        <span className={`icon-tile ${tone}`}><Icon name={icon} /></span>
      </div>
      <p className={`status-value${compact ? ' compact' : ''}${marker ? ' offline-value' : ''}`}>
        {marker && <span className={`availability-dot ${marker}`} aria-hidden="true" />}
        {value}
      </p>
      <p className="status-detail">{detail}</p>
    </article>
  )
}

export default StatusCard
