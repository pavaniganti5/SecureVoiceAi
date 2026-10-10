import { Icon } from './Icons.jsx'

function formatTimestamp(timestamp) {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime())
    ? timestamp
    : new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
}

function formatEventType(eventType) {
  if (eventType === 'person_entered_roi') return 'Person entered monitored region'
  return eventType.replaceAll('_', ' ')
}

function AlertsTable({ alerts, error, isLoading, onRefresh }) {
  return (
    <>
      <div className="alerts-toolbar">
        <span className="alerts-source-note">Most recent MongoDB records · newest first</span>
        <button
          className="text-button"
          disabled={isLoading}
          onClick={onRefresh}
          type="button"
        >
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error ? (
        <div className="alerts-state alerts-error" role="alert">
          <p>Could not load alert history: {error}</p>
          <button className="button button-secondary" onClick={onRefresh} type="button">
            Try again
          </button>
        </div>
      ) : isLoading && alerts.length === 0 ? (
        <p className="alerts-state" role="status">Loading real alert history…</p>
      ) : alerts.length === 0 ? (
        <p className="alerts-state">No recorded security alerts yet. Analyze a video clip to create a real entry.</p>
      ) : (
        <div className="table-wrap">
          <table className="alerts-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Event type</th>
                <th scope="col">Alert message</th>
                <th scope="col">Status / source</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.event_id}>
                  <td>{formatTimestamp(alert.timestamp)}</td>
                  <td>
                    <span className="event-cell">
                      <span className="event-icon"><Icon name="bell" /></span>
                      {formatEventType(alert.event_type)}
                    </span>
                  </td>
                  <td className="alert-message-cell" title={alert.alert_message}>
                    {alert.alert_message}
                  </td>
                  <td>
                    <span className="event-status">{alert.detection_status}</span>
                    <span className="alert-source">{alert.source.replaceAll('_', ' ')}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export default AlertsTable
